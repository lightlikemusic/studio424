# 424

An insert effect plugin for Akai MPC standalone hardware, by Lightlike.

_Describe what the plugin does here. This file is included in the distributable zip._

## Build

```
python tools/build.py plugins/424
python tools/package.py plugins/424
```

## Project layout

- `plugin.json` - manifest (name, manufacturer, uid). The `uid` must match the C++ `uniqueId`.
- `src/Plugin424.cpp` - the plugin source (parameters and DSP).
- `ui.json` - which parameters appear on the MPC screen, in which order.
- `build/` - build output (the deployable `Lightlike - VST - 424` folder lives here).
- `dist/` - zips produced by `package.py`.
