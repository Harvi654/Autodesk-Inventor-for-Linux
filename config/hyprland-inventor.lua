-- Hyprland >= 0.55 (Lua config) rules for Autodesk Inventor under Wine/XWayland.
-- Paste into ~/.config/hypr/hyprland.lua (order matters: rules run top to bottom).
-- For the old hyprlang syntax (hyprland.conf, <= 0.54) see hyprland-inventor.conf.

-- Every Autodesk window: no Hyprland decoration and no animation.
-- Inventor draws its own frames and shadows (WPF panels with separate shadow
-- windows) - Hyprland's border/shadow/rounding around those gives the doubled
-- grey outlines. Move animations make windows that follow the cursor (the
-- coordinate/dimension input next to the sketch cursor) lag behind it.
hl.window_rule({
  name = "inventor-plain",
  match = { class = [[^(inventor\.exe|adsklicensingagent\.exe|adskidentitymanager\.exe)$]] },
  decorate = false,
  no_anim = true,
  no_blur = true,
  no_dim = true,
  -- fully opaque even with decoration active/inactive_opacity < 1 (otherwise the
  -- main window shows the blurred wallpaper when a tool dialog takes the focus)
  opaque = true,
  no_shadow = true,
  border_size = 0,
  rounding = 0,
  no_follow_mouse = true,
  -- Wine asks for fullscreen on any caption-less window covering the monitor;
  -- the right-click marking menu overlay is one. Fullscreened, Hyprland stops
  -- drawing Inventor under it. Super+F still works (not an app request).
  suppress_event = "fullscreen maximize fullscreenoutput",
})

-- Dialogs and tool panels float; tiling them breaks their layout.
hl.window_rule({
  name = "inventor-float",
  match = { class = [[^(inventor\.exe|adsklicensingagent\.exe|adskidentitymanager\.exe)$]] },
  float = true,
})

-- The main window tiles (its title starts with "Autodesk Inventor").
hl.window_rule({
  name = "inventor-main",
  match = { class = [[^inventor\.exe$]], title = [[^Autodesk Inventor.*]] },
  tile = true,
})
