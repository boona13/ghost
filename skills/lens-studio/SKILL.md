---
name: lens-studio
description: Expert guidance for Snap Lens Studio AR development. Use this skill when the user is working on AR lenses, effects, Spectacles integration, or needs help with Lens Studio scripting and optimization.
triggers:
  - lens studio
  - lens studio 5
  - lens studio 5.0
  - snap lens
  - snapchat lens
  - AR effect
  - AR lens
  - spectacles
  - spectacles AR
  - lens script
  - lens scripting
  - snap AR
  - lens optimization
  - lens performance
  - augmented reality
  - face effects
  - face mesh
  - face tracking
  - hand tracking
  - hand effects
  - world mesh
  - world tracking
  - surface tracking
  - persistent storage
  - lens cloud
  - lens studio typescript
  - lens audio
  - audio effect
  - media library
  - remote assets
  - vortex
  - material editor
  - particle system
  - post effect
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
var updateEvent = script.createEvent("UpdateEvent");
updateEvent.bind(function(eventData) {
    var deltaTime = eventData.getDeltaTime();
    // Your update logic
});
```

### 3. Screen Transform Helpers

Common patterns for 2D/3D interaction:

```javascript
function screenToWorld(screenPos, cam) {
    var transform = cam.getSceneObject().getTransform();
    var forward = transform.forward;
    var right = transform.right;
    var up = transform.up;
    
    var x = (screenPos.x / 2) - 1;
    var y = (screenPos.y / 2) - 1;
    
    var worldPos = transform.getWorldPosition()
        .add(right.uniformScale(x))
        .add(up.uniformScale(y))
        .add(forward.uniformScale(10));
    
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
var worldTracking = global.scene.getComponent("Component.WorldTracking");
if (worldTracking) {
    worldTracking.onSurfaceFound = function(surface) {
        surface.getTransform().setWorldPosition(hitPosition);
    };
}
```

## Persistent Storage (Lens Cloud)

```javascript
var Storage = require("Storage");

// Write
Storage.set("user_score", 1000);
Storage.set("unlocked_items", ["hat", "glasses"]);

// Read
var score = Storage.get("user_score") || 0;
var items = Storage.get("unlocked_items") || [];

// Delete
Storage.remove("user_score");

// Clear all
Storage.clear();
```

## TypeScript Support (Lens Studio 5.0+)

Lens Studio 5.0 adds first-class TypeScript support with full autocomplete and type checking:

```typescript
// @input Component.RenderMeshVisual meshVisual
// @input Asset.Material[] materials: Material
// @input float intensity: number = 0.5

class FaceEffectController {
    constructor(private script: ScriptComponent) {}
    
    applyEffect(): void {
        if (!this.script.meshVisual) return;
        
        const material = this.script.materials[0];
        material.mainPass.baseColor = new vec4(1, 1, 1, this.script.intensity);
        this.script.meshVisual.mainMaterial = material;
    }
}

const controller = new FaceEffectController(script);
controller.applyEffect();
```

**Migration tips:**
- Rename `.js` files to `.ts` — LS will compile them
- Use `//@ts-check` in JS files for partial type checking
- Install `@snap/lens-studio-types` for VS Code autocomplete

## Audio Effects

Process microphone input in real-time:

```javascript
// @input Component.AudioComponent audioComponent
// @input Asset.AudioEffectAsset reverbEffect

var audio = script.audioComponent;
audio.audioEffect = script.reverbEffect;

// Access audio features
var audioFeatures = global.scene.getComponent("Component.AudioFeatures");
audioFeatures.onAudioEvent = function(event) {
    var loudness = event.loudness;      // 0-1 volume
    var pitch = event.pitch;            // detected frequency
    var isSpeech = event.isSpeech;      // boolean
    
    // Drive visuals from audio
    script.getTransform().setLocalScale(
        vec3.one().uniformScale(1 + loudness)
    );
};
```

## Media Library (User Gallery)

Allow users to import photos/videos into your lens:

```javascript
// @input Component.Image imageComponent

var MediaLibrary = require("MediaLibrary");

// Open picker (photo or video)
MediaLibrary.openPicker({
    mediaTypes: ["photo", "video"],  // or just ["photo"]
    onComplete: function(asset) {
        if (asset.type === "photo") {
            script.imageComponent.mainPass.baseTex = asset.texture;
        } else if (asset.type === "video") {
            script.videoComponent.mainPass.baseTex = asset.texture;
            asset.control.play();
        }
    },
    onCancel: function() {
        print("User cancelled picker");
    }
});
```

## Remote Assets (Dynamic Loading)

Load assets at runtime to keep initial lens size small:

```javascript
var RemoteAssets = require("RemoteAssets");

// Load from URL
RemoteAssets.loadAsset({
    url: "https://your-cdn.com/lens-assets/effect-pack.zip",
    onComplete: function(asset) {
        // Asset is now available in Resources
        var texture = asset.find("bonus-texture");
        script.meshVisual.mainMaterial.mainPass.baseTex = texture;
    },
    onError: function(error) {
        print("Failed to load: " + error);
    },
    onProgress: function(progress) {
        print("Loading: " + (progress * 100) + "%");
    }
});
```

**Best practices for remote assets:**
- Keep individual assets under 2MB
- Use `.zip` bundles for related assets
- Show loading indicators for user feedback
- Cache downloaded assets with `Storage` API

## Vortex (Visual Scripting)

For designers/non-coders, Lens Studio 5.0 introduces Vortex visual scripting:
- Use for simple logic flows without writing code
- Can coexist with JavaScript/TypeScript
- Best for: simple state machines, animation triggers, UI flows
- Limitations: complex data structures, external API calls

**When to use Vortex vs Script:**
- Vortex: Animation sequences, simple interactions, prototype quickly
- Script: Complex logic, API calls, performance-critical code

## Common Debugging Tips

- Use `print()` for console output (visible in Logger panel)
- **Logger API** for structured debugging:
  ```javascript
  var Logger = require("Logger");
  Logger.log("Category", "Message with value: {0}", myValue);
  Logger.enableCategory("MyDebug");  // Filter in Logger panel
  ```
- Enable **FPS Display** in Preview to monitor performance
- Use **Scene Inspector** to check transform hierarchies at runtime
- Use **Frame Profiler** (Profiler > Frame) to identify bottlenecks
- Test on-device early — preview performance differs from real hardware
- Check **Lens Size** in Project Info — keep under 8MB for optimal loading
- **Spectacles Preview**: Test hand tracking and world mesh on actual hardware
- Use `Diagnostics.setWatch()` to track values in real-time
