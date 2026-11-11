# Rendering Architecture (planned, Phase 6)
Two paths: **interactive viewport** (Three.js now, WebGPU when stable; PBR, HDRI, shadow maps, SSAO) and **high-quality jobs** on a GPU render queue (native path-tracer/Blender-Cycles worker). External renderers (D5, Enscape, Twinmotion, Lumion, Blender) are separate targets reached via their official plugins/file formats; "Mix & Match" only through convertible scene data (glTF/USD + material maps), never by merging incompatible outputs.
AI enhancement (denoise/upscale/lighting) is constrained to be geometry-preserving; a diff check against the model render flags added/removed elements.
Nothing in this document is implemented yet.
