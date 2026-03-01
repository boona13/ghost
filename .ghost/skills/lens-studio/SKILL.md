---
name: lens-studio
description: Expert guidance for Snap Lens Studio AR development. Use this skill when the user is working on AR lenses, effects, Spectacles integration, or needs help with Lens Studio scripting and optimization.
triggers:
  - lens studio
  - snap lens
  - AR effect
  - spectacles
  - lens script
  - snap AR
  - lens optimization
  - augmented reality
  - face mesh
  - hand tracking
  - world mesh
  - persistent storage
  - lens cloud
priority: 10
tools:
  - file_read
  - file_write
  - web_fetch
  - shell_exec
---

# Lens Studio AR Development Guide

This skill provides expert guidance for developing AR lenses and effects using Snap's Lens Studio. From quick prototypes to production-ready Spectacles experiences.

## Project Structure Best Practices

A well-organized Lens Studio project:

```
my-lens/
├── Public/                    # Exposed resources
│   ├── Scripts/
│   │   ├── main.js           # Entry point
│   │   ├── utils.js          # Helper functions
│   │   ├── faceEffects.js    # Face-specific logic
│   │   └── worldEffects.js   # World-tracking logic
│   ├── Materials/
│   ├── Textures/
│   └── Meshes/
├── Resources/                 # Internal assets
└── my-lens.lsproj
```

## Core Patterns

### 1. Script Component Architecture

Use modular script components rather than monolithic scripts:

```javascript
// FaceEffectController.js
// @input Component.ScriptComponent faceMesh
// @input Asset.Material[] effectMaterials
// @input float intensity = 0.5 {"widget":"slider", "min":0, "max":1}

function FaceEffectController() {
    this.applyEffect = function() {
        if (!this.faceMesh) return;
        
        var meshVisual = this.faceMesh.getComponent("Component.RenderMeshVisual");
        if (meshVisual) {
            meshVisual.mainMaterial = this.effectMaterials[0];
            meshVisual.mainMaterial.mainPass.baseColor = new vec4(1, 1, 1, this.intensity);
        }
    };
}

var controller = new FaceEffectController();
controller.applyEffect();
```

### 2. Event-Driven Updates

Use Lens Studio's event system for frame updates:

```javascript
// Prefer this:
var updateEvent = script.createEvent("UpdateEvent");
updateEvent.bind(function(eventData) {
    var deltaTime = eventData.getDeltaTime();
    // Your update logic
});

// Over polling in update()
```

### 3. Screen Transform Helpers

Common patterns for 2D/3D interaction:

```javascript
// Convert screen point to world space
function screenToWorld(screenPos, cam) {
    var transform = cam.getSceneObject().getTransform();
    var forward = transform.forward;
    var right = transform.right;
    var up = transform.up;
    
    // Normalize screen coordinates (-1 to 1)
    var x = (screenPos.x / 2) - 1;
    var y = (screenPos.y / 2) - 1;
    
    var worldPos = transform.getWorldPosition()
        .add(right.uniformScale(x))
        .add(up.uniformScale(y))
        .add(forward.uniformScale(10)); // 10 units in front
    
    return worldPos;
}
```

## Performance Optimization

### Texture Guidelines
- Max texture size: 1024x1024 for most lenses
- Use compressed textures (ASTC for iOS, ETC2 for Android)
- Pool reusable textures
- Avoid runtime texture generation

### Mesh Optimization
- Keep face mesh subdivisions reasonable (default is usually fine)
- Limit draw calls: batch materials where possible
- Use LOD for complex 3D models
- Disable shadows unless essential

### Script Performance
```javascript
// Cache expensive lookups
var cachedTransform = script.getTransform();
var cachedMaterial = script.meshVisual.mainMaterial;

// In update loop, use cached references
// NOT: script.getTransform().getWorldPosition() every frame
```

## Spectacles-Specific Considerations

### Hand Tracking
```javascript
// @input Component.HandTracking handTracking

var hand = script.handTracking;
hand.onHandFound = function() {
    print("Hand detected");
};

hand.onHandLost = function() {
    print("Hand lost");
};

hand.onUpdate = function() {
    var position = hand.getTransform().getWorldPosition();
    var gesture = hand.getGesture(); // open_hand, closed_fist, etc.
};
```

### World Mesh
```javascript
// Access world understanding
var worldTracking = global.scene.getComponent("Component.WorldTracking");
if (worldTracking) {
    worldTracking.onSurfaceFound = function(surface) {
        // Place content on real-world surfaces
        surface.getTransform().setWorldPosition(hitPosition);
    };
}
```

## Persistent Storage (Lens Cloud)

```javascript
// Save user preferences
var Storage = require("Storage");

// Write
Storage.set("user_score", 1000);
Storage.set("unlocked_items", ["hat", "glasses"]);

// Read
var score = Storage.get("user_score") || 0;
var items = Storage.get("unlocked_items") || [];

// Sync to cloud (if Lens Cloud enabled)
Storage.sync();
```

## Debugging Tips

1. **Console Logging**: Use `print()` liberally during development
2. **Visual Helpers**: Add temporary mesh gizmos to visualize transforms
3. **Script Hot-Reload**: Edit scripts externally and re-import
4. **Profiler**: Use Lens Studio's built-in profiler for GPU/CPU metrics
5. **Device Testing**: Test on target devices early and often

## Common Pitfalls

- ❌ Don't create new `vec3`, `quat`, or `mat4` every frame — pool them
- ❌ Don't forget to null-check components before accessing
- ❌ Don't use synchronous `require()` in update loops
- ✅ Do use `script.api` to expose public methods for inter-script communication
- ✅ Do destroy unused SceneObjects to prevent memory leaks
- ✅ Do test on low-end devices, not just your development machine

## Resources

- Lens Studio: https://ar.snap.com/lens-studio
- Scripting Reference: https://docs.snap.com/lens-studio/references/scripting
- Spectacles Dev: https://docs.snap.com/spectacles
- Asset Library: Built-in to Lens Studio (3D models, materials, templates)
