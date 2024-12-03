<p align="center">
  <img src="https://raw.githubusercontent.com/ikz87/yawns/refs/heads/main/assets/yawns-logo.png" width=75%>
</p>

<h1 align="center"> Your Adaptable Widget Notification System </h1>

<p align="center">
<img src="https://github.com/user-attachments/assets/95a246de-d562-44db-a0e5-d461ca2481b3" width=100%> 
</p>


## Table of contents
- [Introduction](#introduction)
- [Features](#features)
- [Examples](#examples)
- [Installing](#installing)


# Introduction

Yawns is a notification manager (or daemon) written out of the necessity for highly customizable, adaptable notifications. Why would your notification for a brightness change look the same as your Spotify song change notification? Or even an email one? This is where Yawns introduces the concept of, uhm, well, __yawns__.

A yawn is a window displaying the contents of a notification. So far, the following yawns are available:
- __Corner yawn__: The most classic notification design. Shows up as a window anchored to one of the corners of your screen. Multiple notifications stack vertically. Ideal for things like e-mail notifications.
- __Center yawn__: Show a notification in the center of the screen. Multiple notifications stack vertically one behind the other. Meant mostly for displaying quick settings changes like volume, brightness or keyboard layout.
- __Media yawn__: Like a corner yawn, but this one shows the notification icon as a spinning vinyl disc and doesn't stack, each new yawn replaces the last one (if it's still open). Your Spotify notifications are gonna look amazing with this one.

When a notification is received, if the hint `yawn_type` is provided (like when running `notify-send hello -h int:yawn_type:1`), the manager will use the specified yawn type to display the notification, following the order from the above list starting from 1.

There are more yawn types to come but you're more than welcome to open an issue suggesting any cool ideas you might have :)

You can read more about how Yawns work in the [wiki](https://github.com/ikz87/yawns/wiki)


# Features
- Full markup on summary and body
- Full control of per-yawn QSS (kinda like CSS)
- Scripting via an external command set in configs
- Completely different yawns (notification windows) based on notification hints
  

# Examples
These are some of the cool notifications I'm currently using yawns for :)

All the notifications below are either sent by applications or through the `notify-send` core util. No extra tool is needed

## A center yawn with a workspace change notification
Featuring some markdown to change font size and color on certain characters, from this [script](https://github.com/ikz87/dots-2.0/blob/personal/Bscripts/wp_switcher.sh)

![image](https://github.com/user-attachments/assets/9187da2f-8f8c-4fd2-a724-f53bfbfaa173)


## A center yawn with a brightness/volume change notification
With corresponding icon and bar percentage, from these [brightness](https://github.com/ikz87/dots-2.0/blob/personal/Bscripts/brightness.sh) and [volume](https://github.com/ikz87/dots-2.0/blob/personal/Bscripts/volume.sh) scripts

![image](https://github.com/user-attachments/assets/8bde0777-3b16-4762-88ae-886e2e1f0815)
![image](https://github.com/user-attachments/assets/1235ad6d-f6a9-4975-ab07-c840ad8c3e8e)

## A corner yawn with a text message with action buttons (Whatsapp)
![image](https://github.com/user-attachments/assets/5f4f4fdf-eeab-4e1b-84f0-b5ab99b43001)

## A corner yawn with a battery warning notification
From this [script](https://github.com/ikz87/dots-2.0/blob/main/Configs/eww/mybar/scripts/battery_info)

![image](https://github.com/user-attachments/assets/bd98992a-9f3b-4af5-8ce8-9e0e4e08d506)

## A media yawn with a Spotify notification
![output](https://github.com/user-attachments/assets/4a584ca7-029f-45dc-874b-ff8cc08cb3db)



# Installing
Either install from the official [AUR package](https://aur.archlinux.org/packages/yawns) or run `install.sh` as root.
