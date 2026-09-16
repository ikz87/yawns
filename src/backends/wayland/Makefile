# Native Wayland helper for yawns.
#
# Builds libyawns_wayland.so, a small C++ shim that attaches Qt's existing
# wl_surface to zwlr_layer_shell_v1 and exposes a plain C ABI (consumed from
# backends/Wayland.py through ctypes). It never opens its own Wayland
# connection: everything happens on the wl_display owned by Qt.

PKG_CONFIG ?= pkg-config
CC ?= gcc
CXX ?= g++
WAYLAND_SCANNER ?= wayland-scanner

QT_VERSION     := $(shell $(PKG_CONFIG) --modversion Qt6Core)
QT_INCLUDEDIR  := $(shell $(PKG_CONFIG) --variable=includedir Qt6Core)

QT_CFLAGS := $(shell $(PKG_CONFIG) --cflags Qt6Core Qt6Gui Qt6Widgets Qt6WaylandClient)
QT_LIBS   := $(shell $(PKG_CONFIG) --libs   Qt6Core Qt6Gui Qt6Widgets Qt6WaylandClient)
WL_CFLAGS := $(shell $(PKG_CONFIG) --cflags wayland-client)
WL_LIBS   := $(shell $(PKG_CONFIG) --libs   wayland-client)

# Qt private headers (QtWaylandClient shell-integration API and QPA headers).
QT_PRIVATE_INC := \
	-I$(QT_INCLUDEDIR)/QtCore/$(QT_VERSION) \
	-I$(QT_INCLUDEDIR)/QtCore/$(QT_VERSION)/QtCore \
	-I$(QT_INCLUDEDIR)/QtGui/$(QT_VERSION) \
	-I$(QT_INCLUDEDIR)/QtGui/$(QT_VERSION)/QtGui \
	-I$(QT_INCLUDEDIR)/QtWidgets/$(QT_VERSION) \
	-I$(QT_INCLUDEDIR)/QtWidgets/$(QT_VERSION)/QtWidgets \
	-I$(QT_INCLUDEDIR)/QtWaylandClient/$(QT_VERSION) \
	-I$(QT_INCLUDEDIR)/QtWaylandClient/$(QT_VERSION)/QtWaylandClient \
	-I$(QT_INCLUDEDIR)/QtWaylandGlobal/$(QT_VERSION) \
	-I$(QT_INCLUDEDIR)/QtWaylandGlobal/$(QT_VERSION)/QtWaylandGlobal

BUILD_DIR := build
TARGET    := $(BUILD_DIR)/libyawns_wayland.so

PROTOCOLS := \
	protocols/wlr-layer-shell-unstable-v1.xml \
	protocols/wlr-foreign-toplevel-management-unstable-v1.xml \
	protocols/xdg-shell.xml

PROTO_NAMES := \
	wlr-layer-shell-unstable-v1 \
	wlr-foreign-toplevel-management-unstable-v1 \
	xdg-shell

GEN_HEADERS := $(addprefix $(BUILD_DIR)/,$(addsuffix -client-protocol.h,$(PROTO_NAMES)))
GEN_SOURCES := $(addprefix $(BUILD_DIR)/,$(addsuffix -protocol.c,$(PROTO_NAMES)))
GEN_OBJECTS := $(addprefix $(BUILD_DIR)/,$(addsuffix -protocol.o,$(PROTO_NAMES)))

.PHONY: all clean print-config

all: $(TARGET)

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/%-client-protocol.h: protocols/%.xml | $(BUILD_DIR)
	$(WAYLAND_SCANNER) client-header $< $@

$(BUILD_DIR)/%-protocol.c: protocols/%.xml | $(BUILD_DIR)
	$(WAYLAND_SCANNER) private-code $< $@

# The generated protocol code is C and must be built as C: in C++ a
# namespace-scope `const` has internal linkage, which would hide the
# wl_interface symbols and break the link.
$(BUILD_DIR)/%-protocol.o: $(BUILD_DIR)/%-protocol.c | $(BUILD_DIR)
	$(CC) -fPIC -O2 $(WL_CFLAGS) -I$(BUILD_DIR) -c $< -o $@

$(BUILD_DIR)/yawns_wayland.o: yawns_wayland.cpp $(GEN_HEADERS) | $(BUILD_DIR)
	$(CXX) -std=c++17 -fPIC -O2 -Wall -Wextra \
		$(QT_CFLAGS) $(QT_PRIVATE_INC) $(WL_CFLAGS) -I$(BUILD_DIR) \
		-c $< -o $@

$(TARGET): $(BUILD_DIR)/yawns_wayland.o $(GEN_OBJECTS)
	$(CXX) -shared -o $@ $^ $(QT_LIBS) $(WL_LIBS)

print-config:
	@echo "QT_VERSION=$(QT_VERSION)"
	@echo "QT_PRIVATE_INC=$(QT_PRIVATE_INC)"
	@echo "QT_CFLAGS=$(QT_CFLAGS)"
	@echo "QT_LIBS=$(QT_LIBS)"

clean:
	rm -rf $(BUILD_DIR)
