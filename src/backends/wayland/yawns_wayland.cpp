// yawns_wayland.cpp
//
// Small native Wayland wrapper for yawns.
//
// Wayland does not let an application place a top-level window at arbitrary
// coordinates, and Qt does not expose the wlr-layer-shell protocol through its
// public API. This shim bridges both gaps:
//
//   * It reuses the wl_surface / wl_display that Qt already created for each
//     yawn and gives that surface the zwlr_layer_surface_v1 role, so the window
//     becomes an anchored layer surface (always on top, no keyboard grab, no
//     exclusive zone).
//   * Anchor + margins are exposed through a plain C ABI. Moving a yawn is a
//     matter of updating its margins and committing its surface.
//   * Fullscreen detection is done with zwlr_foreign_toplevel_manager_v1,
//     which reports per-toplevel "activated" and "fullscreen" state.
//
// Everything runs on the wl_display owned by Qt; no second connection is
// opened and no separate event loop is required.
//
// SPDX-License-Identifier: GPL-3.0-or-later

#include <cstdint>
#include <cstring>

#include <QCoreApplication>
#include <QGuiApplication>
#include <QEvent>
#include <QHash>
#include <QMargins>
#include <QObject>
#include <QPointer>
#include <QScreen>
#include <QSize>
#include <QString>
#include <QWindow>

#include <QtWaylandClient/private/qwaylandclientshellapi_p.h>
#include <QtWaylandClient/private/qwaylanddisplay_p.h>
#include <QtWaylandClient/private/qwaylandscreen_p.h>
#include <QtWaylandClient/private/qwaylandwindow_p.h>

#include <wayland-client.h>

#include "wlr-layer-shell-unstable-v1-client-protocol.h"
#include "wlr-foreign-toplevel-management-unstable-v1-client-protocol.h"

using QtWaylandClient::QWaylandDisplay;
using QtWaylandClient::QWaylandScreen;
using QtWaylandClient::QWaylandShellIntegration;
using QtWaylandClient::QWaylandShellSurface;
using QtWaylandClient::QWaylandWindow;

namespace {

// ---------------------------------------------------------------------------
// Per-window configuration
// ---------------------------------------------------------------------------

struct LayerConfig {
    uint32_t layer = ZWLR_LAYER_SHELL_V1_LAYER_TOP;
    uint32_t anchor = ZWLR_LAYER_SURFACE_V1_ANCHOR_TOP
                    | ZWLR_LAYER_SURFACE_V1_ANCHOR_LEFT;
    uint32_t keyboard = ZWLR_LAYER_SURFACE_V1_KEYBOARD_INTERACTIVITY_NONE;
    int32_t exclusive = 0;
    int32_t marginTop = 0;
    int32_t marginRight = 0;
    int32_t marginBottom = 0;
    int32_t marginLeft = 0;
    int32_t width = 0;
    int32_t height = 0;
    QString scope = QStringLiteral("yawns");
    QPointer<QScreen> screen;
};

QHash<QWindow *, LayerConfig> g_configs;
class LayerSurface;
QHash<QWindow *, LayerSurface *> g_surfaces;

zwlr_layer_shell_v1 *g_layerShell = nullptr;
zwlr_foreign_toplevel_manager_v1 *g_ftlManager = nullptr;
wl_display *g_wlDisplay = nullptr;
bool g_globalsBound = false;

// ---------------------------------------------------------------------------
// Window registry: forget everything when a yawn's QWindow is destroyed.
// ---------------------------------------------------------------------------

class WindowRegistry : public QObject
{
public:
    bool eventFilter(QObject *object, QEvent *event) override
    {
        if (event->type() == QEvent::Destroy) {
            auto *window = static_cast<QWindow *>(object);
            g_configs.remove(window);
        }
        return QObject::eventFilter(object, event);
    }
};

WindowRegistry *g_registry = nullptr;
WindowRegistry *registry()
{
    if (!g_registry)
        g_registry = new WindowRegistry();
    return g_registry;
}

// ---------------------------------------------------------------------------
// Layer surface
// ---------------------------------------------------------------------------

wl_output *outputForConfig(const LayerConfig &config, QWindow *window)
{
    QScreen *screen = config.screen.data();
    if (!screen)
        screen = window->screen();
    if (!screen)
        screen = QGuiApplication::primaryScreen();
    if (!screen)
        return nullptr;

    if (auto *waylandScreen = dynamic_cast<QWaylandScreen *>(screen->handle()))
        return waylandScreen->output();
    return nullptr;
}

class LayerSurface : public QWaylandShellSurface
{
public:
    explicit LayerSurface(QWaylandWindow *window);

    ~LayerSurface() override;

    bool isExposed() const override { return m_configured; }
    void applyConfigure() override;
    void setWindowSize(const QSize &size) override;
    bool requestActivate() override { return false; }
    bool requestActivateOnShow() override { return false; }

    void apply(const LayerConfig &config, bool commit);
    void commitSurface();

    static void onConfigure(void *data, zwlr_layer_surface_v1 *surface,
                            uint32_t serial, uint32_t width, uint32_t height);
    static void onClosed(void *data, zwlr_layer_surface_v1 *surface);

private:
    void handleConfigure(uint32_t serial, uint32_t width, uint32_t height);
    void handleClosed();

    zwlr_layer_surface_v1 *m_surface = nullptr;
    QSize m_pendingSize;
    bool m_configured = false;
};

const zwlr_layer_surface_v1_listener kLayerSurfaceListener = {
    &LayerSurface::onConfigure,
    &LayerSurface::onClosed,
};

LayerSurface::LayerSurface(QWaylandWindow *window)
    : QWaylandShellSurface(window)
{
    QWindow *qwindow = window->window();

    LayerConfig config;
    const auto it = g_configs.constFind(qwindow);
    if (it != g_configs.constEnd())
        config = it.value();

    wl_output *output = outputForConfig(config, qwindow);
    const QByteArray scope = config.scope.toUtf8();
    m_surface = zwlr_layer_shell_v1_get_layer_surface(
        g_layerShell, window->wlSurface(), output, config.layer, scope.constData());
    zwlr_layer_surface_v1_add_listener(m_surface, &kLayerSurfaceListener, this);

    g_surfaces.insert(qwindow, this);
    apply(config, true);
}

LayerSurface::~LayerSurface()
{
    if (window()) {
        QWindow *qwindow = window()->window();
        if (qwindow)
            g_surfaces.remove(qwindow);
    }
    if (m_surface) {
        zwlr_layer_surface_v1_destroy(m_surface);
        m_surface = nullptr;
    }
}

void LayerSurface::apply(const LayerConfig &config, bool commit)
{
    if (!m_surface)
        return;

    zwlr_layer_surface_v1_set_size(m_surface, config.width, config.height);
    zwlr_layer_surface_v1_set_anchor(m_surface, config.anchor);
    zwlr_layer_surface_v1_set_margin(m_surface, config.marginTop,
                                     config.marginRight, config.marginBottom,
                                     config.marginLeft);
    zwlr_layer_surface_v1_set_exclusive_zone(m_surface, config.exclusive);
    zwlr_layer_surface_v1_set_keyboard_interactivity(m_surface, config.keyboard);
    if (zwlr_layer_surface_v1_get_version(m_surface)
        >= ZWLR_LAYER_SURFACE_V1_SET_LAYER_SINCE_VERSION) {
        zwlr_layer_surface_v1_set_layer(m_surface, config.layer);
    }

    if (commit)
        commitSurface();
}

void LayerSurface::commitSurface()
{
    if (m_surface && window() && window()->wlSurface())
        wl_surface_commit(window()->wlSurface());
}

void LayerSurface::handleConfigure(uint32_t serial, uint32_t width,
                                   uint32_t height)
{
    zwlr_layer_surface_v1_ack_configure(m_surface, serial);
    m_pendingSize = QSize(static_cast<int>(width), static_cast<int>(height));

    if (!m_configured) {
        m_configured = true;
        applyConfigure();
        window()->updateExposure();
    } else {
        // Later configures are resizes; let Qt apply them when it can.
        window()->applyConfigureWhenPossible();
    }
}

void LayerSurface::handleClosed()
{
    if (window() && window()->window())
        window()->window()->close();
}

void LayerSurface::applyConfigure()
{
    window()->resizeFromApplyConfigure(m_pendingSize);
}

void LayerSurface::setWindowSize(const QSize &size)
{
    if (!m_surface || !window() || !window()->window())
        return;

    const auto it = g_configs.constFind(window()->window());
    if (it != g_configs.constEnd() && it->width == 0 && it->height == 0) {
        // The compositor owns sizing on this axis because the client asked for
        // it; let it know the new content size.
        zwlr_layer_surface_v1_set_size(m_surface, size.width(), size.height());
    }
}

void LayerSurface::onConfigure(void *data, zwlr_layer_surface_v1 *surface,
                               uint32_t serial, uint32_t width, uint32_t height)
{
    Q_UNUSED(surface);
    static_cast<LayerSurface *>(data)->handleConfigure(serial, width, height);
}

void LayerSurface::onClosed(void *data, zwlr_layer_surface_v1 *surface)
{
    Q_UNUSED(surface);
    static_cast<LayerSurface *>(data)->handleClosed();
}

// ---------------------------------------------------------------------------
// Shell integration: makes Qt create a layer surface instead of an xdg one.
// ---------------------------------------------------------------------------

class LayerIntegration : public QWaylandShellIntegration
{
public:
    bool initialize(QWaylandDisplay *) override { return g_layerShell != nullptr; }

    QWaylandShellSurface *createShellSurface(QWaylandWindow *window) override
    {
        return new LayerSurface(window);
    }
};

LayerIntegration *g_integration = nullptr;

// ---------------------------------------------------------------------------
// Global binding (registry) for layer shell + foreign toplevel
// ---------------------------------------------------------------------------

// Foreign toplevel state. The protocol reports states as an array of enum
// entries, so we turn it into a bitmask.
QHash<zwlr_foreign_toplevel_handle_v1 *, uint32_t> g_toplevelStates;
int g_fullscreenState = 0;
void (*g_fsCallback)(int) = nullptr;

void recomputeFullscreen()
{
    bool fullscreen = false;
    for (uint32_t mask : g_toplevelStates) {
        const bool isFullscreen =
            mask & (1u << ZWLR_FOREIGN_TOPLEVEL_HANDLE_V1_STATE_FULLSCREEN);
        const bool isActive =
            mask & (1u << ZWLR_FOREIGN_TOPLEVEL_HANDLE_V1_STATE_ACTIVATED);
        if (isFullscreen && isActive) {
            fullscreen = true;
            break;
        }
    }

    const int value = fullscreen ? 1 : 0;
    if (value != g_fullscreenState) {
        g_fullscreenState = value;
        if (g_fsCallback)
            g_fsCallback(value);
    }
}

void ftlTitle(void *, zwlr_foreign_toplevel_handle_v1 *, const char *) {}
void ftlAppId(void *, zwlr_foreign_toplevel_handle_v1 *, const char *) {}
void ftlOutputEnter(void *, zwlr_foreign_toplevel_handle_v1 *, wl_output *) {}
void ftlOutputLeave(void *, zwlr_foreign_toplevel_handle_v1 *, wl_output *) {}

void ftlState(void *, zwlr_foreign_toplevel_handle_v1 *handle, wl_array *state)
{
    uint32_t mask = 0;
    const auto *entries = static_cast<const uint32_t *>(state->data);
    const size_t count = state->size / sizeof(uint32_t);
    for (size_t i = 0; i < count; ++i)
        mask |= (1u << entries[i]);
    g_toplevelStates.insert(handle, mask);
}

void ftlDone(void *, zwlr_foreign_toplevel_handle_v1 *)
{
    recomputeFullscreen();
}

void ftlClosed(void *, zwlr_foreign_toplevel_handle_v1 *handle)
{
    g_toplevelStates.remove(handle);
    zwlr_foreign_toplevel_handle_v1_destroy(handle);
    recomputeFullscreen();
}

void ftlParent(void *, zwlr_foreign_toplevel_handle_v1 *,
               zwlr_foreign_toplevel_handle_v1 *) {}

const zwlr_foreign_toplevel_handle_v1_listener kToplevelListener = {
    &ftlTitle,       &ftlAppId,  &ftlOutputEnter, &ftlOutputLeave,
    &ftlState,       &ftlDone,   &ftlClosed,      &ftlParent,
};

void ftlToplevel(void *, zwlr_foreign_toplevel_manager_v1 *,
                 zwlr_foreign_toplevel_handle_v1 *handle)
{
    zwlr_foreign_toplevel_handle_v1_add_listener(handle, &kToplevelListener,
                                                 nullptr);
    g_toplevelStates.insert(handle, 0);
}

void ftlFinished(void *, zwlr_foreign_toplevel_manager_v1 *manager)
{
    zwlr_foreign_toplevel_manager_v1_destroy(manager);
    g_ftlManager = nullptr;
}

const zwlr_foreign_toplevel_manager_v1_listener kManagerListener = {
    &ftlToplevel,
    &ftlFinished,
};

void registryGlobal(void *, wl_registry *registry, uint32_t name,
                    const char *interface, uint32_t version)
{
    if (std::strcmp(interface, zwlr_layer_shell_v1_interface.name) == 0) {
        const uint32_t wanted = version < 5 ? version : 5;
        g_layerShell = static_cast<zwlr_layer_shell_v1 *>(wl_registry_bind(
            registry, name, &zwlr_layer_shell_v1_interface, wanted));
    } else if (std::strcmp(interface,
                          zwlr_foreign_toplevel_manager_v1_interface.name)
               == 0) {
        const uint32_t wanted = version < 3 ? version : 3;
        g_ftlManager =
            static_cast<zwlr_foreign_toplevel_manager_v1 *>(wl_registry_bind(
                registry, name, &zwlr_foreign_toplevel_manager_v1_interface,
                wanted));
        zwlr_foreign_toplevel_manager_v1_add_listener(g_ftlManager,
                                                      &kManagerListener, nullptr);
    }
}

void registryGlobalRemove(void *, wl_registry *, uint32_t) {}

const wl_registry_listener kRegistryListener = {
    &registryGlobal,
    &registryGlobalRemove,
};

int ensureGlobals(wl_display *display)
{
    if (g_globalsBound)
        return g_layerShell ? 0 : -1;
    if (!display)
        return -1;

    g_wlDisplay = display;

    wl_registry *registry = wl_display_get_registry(display);
    wl_registry_add_listener(registry, &kRegistryListener, nullptr);

    // One roundtrip to learn the globals, one to receive the initial events of
    // the objects we bound (e.g. the current toplevel list).
    wl_display_roundtrip(display);
    wl_display_roundtrip(display);

    g_globalsBound = true;
    return g_layerShell ? 0 : -1;
}

QWaylandWindow *waylandWindowFor(void *qwindow)
{
    if (!qwindow)
        return nullptr;
    auto *window = static_cast<QWindow *>(qwindow);
    return dynamic_cast<QWaylandWindow *>(window->handle());
}

} // namespace

// ---------------------------------------------------------------------------
// C ABI
// ---------------------------------------------------------------------------

extern "C" {

// Returns 0 on success, a negative value if yawns is not running on Wayland or
// layer shell is unavailable.
int yawns_wayland_init(void)
{
    auto *wa = qGuiApp->nativeInterface<
        QNativeInterface::QWaylandApplication>();
    if (!wa)
        return -1;
    wl_display *display = wa->display();
    if (!display)
        return -1;
    return ensureGlobals(display);
}

int yawns_wayland_has_layer_shell(void)
{
    return g_layerShell ? 1 : 0;
}

int yawns_layer_attach(void *qwindow, uint32_t layer, uint32_t anchor,
                       int32_t marginTop, int32_t marginRight,
                       int32_t marginBottom, int32_t marginLeft,
                       uint32_t exclusive, uint32_t keyboard, const char *scope,
                       void *qscreen)
{
    QWaylandWindow *waylandWindow = waylandWindowFor(qwindow);
    if (!waylandWindow)
        return -1;

    auto *window = static_cast<QWindow *>(qwindow);

    LayerConfig config;
    config.layer = layer;
    config.anchor = anchor;
    config.keyboard = keyboard;
    config.exclusive = exclusive;
    config.marginTop = marginTop;
    config.marginRight = marginRight;
    config.marginBottom = marginBottom;
    config.marginLeft = marginLeft;
    config.scope = scope ? QString::fromUtf8(scope) : QStringLiteral("yawns");
    config.screen = static_cast<QScreen *>(qscreen);
    g_configs.insert(window, config);
    window->installEventFilter(registry());

    if (!g_layerShell) {
        wl_display *display =
            waylandWindow->display() ? waylandWindow->display()->wl_display()
                                     : nullptr;
        if (ensureGlobals(display) != 0)
            return -2;
    }

    if (!g_integration)
        g_integration = new LayerIntegration();
    if (!g_integration->initialize(waylandWindow->display()))
        return -3;
    waylandWindow->setShellIntegration(g_integration);

    if (auto *surface = g_surfaces.value(window))
        surface->apply(config, true);

    return 0;
}

int yawns_layer_set_geometry(void *qwindow, uint32_t anchor, int32_t marginTop,
                             int32_t marginRight, int32_t marginBottom,
                             int32_t marginLeft, int32_t width, int32_t height)
{
    auto *window = static_cast<QWindow *>(qwindow);
    if (!window)
        return -1;

    auto it = g_configs.find(window);
    if (it == g_configs.end())
        return -2;

    it->anchor = anchor;
    it->marginTop = marginTop;
    it->marginRight = marginRight;
    it->marginBottom = marginBottom;
    it->marginLeft = marginLeft;
    it->width = width;
    it->height = height;

    if (auto *surface = g_surfaces.value(window))
        surface->apply(*it, true);

    return 0;
}

int yawns_layer_set_layer(void *qwindow, uint32_t layer)
{
    auto *window = static_cast<QWindow *>(qwindow);
    if (!window)
        return -1;
    auto it = g_configs.find(window);
    if (it == g_configs.end())
        return -2;
    it->layer = layer;
    if (auto *surface = g_surfaces.value(window))
        surface->apply(*it, true);
    return 0;
}

int yawns_layer_set_anchors(void *qwindow, uint32_t anchor)
{
    auto *window = static_cast<QWindow *>(qwindow);
    if (!window)
        return -1;
    auto it = g_configs.find(window);
    if (it == g_configs.end())
        return -2;
    it->anchor = anchor;
    if (auto *surface = g_surfaces.value(window))
        surface->apply(*it, true);
    return 0;
}

int yawns_layer_set_keyboard_interactivity(void *qwindow, uint32_t keyboard)
{
    auto *window = static_cast<QWindow *>(qwindow);
    if (!window)
        return -1;
    auto it = g_configs.find(window);
    if (it == g_configs.end())
        return -2;
    it->keyboard = keyboard;
    if (auto *surface = g_surfaces.value(window))
        surface->apply(*it, true);
    return 0;
}

int yawns_layer_set_exclusive_zone(void *qwindow, int32_t exclusive)
{
    auto *window = static_cast<QWindow *>(qwindow);
    if (!window)
        return -1;
    auto it = g_configs.find(window);
    if (it == g_configs.end())
        return -2;
    it->exclusive = exclusive;
    if (auto *surface = g_surfaces.value(window))
        surface->apply(*it, true);
    return 0;
}

void yawns_layer_detach(void *qwindow)
{
    auto *window = static_cast<QWindow *>(qwindow);
    if (!window)
        return;
    g_configs.remove(window);
    if (auto *surface = g_surfaces.value(window))
        surface->commitSurface();
}

void yawns_fs_set_callback(void (*callback)(int))
{
    g_fsCallback = callback;
    if (callback)
        callback(g_fullscreenState);
}

int yawns_fs_start(void)
{
    return g_ftlManager ? 1 : 0;
}

void yawns_fs_stop(void)
{
    g_fsCallback = nullptr;
}

} // extern "C"
