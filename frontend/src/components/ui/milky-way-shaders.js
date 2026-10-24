// Galaxy particle shaders from the supplied Hyperiux Vault Milky Way reference.
export const CFG = {
  colorParticleRatio: .01, baseSize: 8, sparkleSize: 12, twinkleSpeed: 4.5,
  colorLevels: { core: 1.15, mid: 1, outer: .9, sparkle: 1.1 },
}
export const SMOKE_CFG = {
  particleSize: 92, opacity: .05,
  colorLevels: { core: 1.25, cyan: 1.05, magenta: 1.1, violet: .95, outer: .75 },
}
export const SIM_FRAG = /* glsl */`
precision highp float;
uniform sampler2D uPosition;
uniform sampler2D uData;
uniform float uDelta;
uniform float uTime;
varying vec2 vUv;
void main(){
 vec4 pos = texture2D(uPosition, vUv);
 vec4 data = texture2D(uData, vUv);
 vec3 p = pos.xyz;
 float phase = pos.w;
 float radiusFrac = data.x;
 float seed = data.y;
 float orbSpeed = data.z;
 float r = length(p.xy) + 0.0001;
 float vTan = orbSpeed * (r / (r + 0.28));
 float omega = vTan / r;
 float dAngle = omega * uDelta * .2;
 float cosA = cos(dAngle);
 float sinA = sin(dAngle);
 float nx = p.x * cosA - p.y * sinA;
 float ny = p.x * sinA + p.y * cosA;
 p.x = nx;
 p.y = ny;
 p.z += sin(uTime * 0.2 + seed * 6.28318) * 0.0001;
 phase = mod(phase + uDelta * (0.018 + seed * 0.008), 1.0);
 gl_FragColor = vec4(p, phase);
}
`
export const PARTICLE_VERT = /* glsl */`
precision highp float;
uniform sampler2D uPosition;
uniform float uPixelRatio;
uniform float uParticleSize;
attribute vec2 aRef;
attribute float aRadiusFrac;
attribute float aSeed;
attribute float aColor;
varying float vRadiusFrac;
varying float vPhase;
varying float vSeed;
varying float vColor;
void main(){
 vec4 posData = texture2D(uPosition, aRef);
 vec3 pos = posData.xyz;
 vPhase = posData.w;
 vRadiusFrac = aRadiusFrac;
 vSeed = aSeed;
 vColor = aColor;
 vec4 mvPos = modelViewMatrix * vec4(pos, 1.0);
 float depth = -mvPos.z;
 float isSpecial = step(${(1.0 - CFG.colorParticleRatio).toFixed(3)}, aColor);
 float sizeFactor = pow(1.0 - aRadiusFrac, 1.3);
 float normalSz = mix(0.5, ${CFG.baseSize.toFixed(1)}, sizeFactor) * (0.7 + aSeed * 0.5);
 float specialSz = mix(
 ${CFG.sparkleSize.toFixed(1)} * 0.6,
 ${CFG.sparkleSize.toFixed(1)},
 aSeed
 );
 float sz = mix(normalSz, specialSz, isSpecial);
 sz *= uParticleSize;
 sz *= (420.0 / max(depth, 0.1)) * uPixelRatio;
 float maxSize = mix(
 (${CFG.baseSize.toFixed(1)} * (2.0 + aSeed * 1.0)),
 (${CFG.sparkleSize.toFixed(1)} * (2.0 + aSeed * 1.0)),
 isSpecial
 ) * uParticleSize;
 gl_PointSize = clamp(sz, 0.4, maxSize);
 gl_Position = projectionMatrix * mvPos;
}
`
export const PARTICLE_FRAG = /* glsl */`
precision highp float;
varying float vRadiusFrac;
varying float vPhase;
varying float vSeed;
varying float vColor;
uniform vec3 uCoreColor;
uniform vec3 uAccentColor;
uniform vec3 uOuterColor;
void main(){
 vec2 uv = gl_PointCoord - 0.5;
 float r = length(uv) * 2.0;
 if(r > 1.0) discard;
 float cp = exp(-r * r * 14.0);
 float halo = exp(-r * r * 3.0) * 0.30;
 float disc = clamp(cp + halo, 0.0, 1.0);
 float dispersion = pow(1.0 - vRadiusFrac, 1.05);
 float coreBulge = smoothstep(0.22, 0.0, vRadiusFrac) * 0.55;
 float intensity = clamp(dispersion + coreBulge, 0.0, 1.0);
 float tRate = 2.5 + vSeed * ${CFG.twinkleSpeed.toFixed(1)};
 float twinkle = 0.78 + 0.22 * sin(vPhase * 6.28318 * tRate + vSeed * 17.3);
 intensity *= twinkle;
 float isSpecial = step(${(1.0 - CFG.colorParticleRatio).toFixed(3)}, vColor);
 vec3 nCore = uCoreColor * ${CFG.colorLevels.core.toFixed(2)};
 vec3 nMid = mix(uCoreColor, uAccentColor, 0.7) * ${CFG.colorLevels.mid.toFixed(2)};
 vec3 nOuter = uOuterColor * ${CFG.colorLevels.outer.toFixed(2)};
 vec3 normalCol = mix(nCore, nMid, smoothstep(0.00, 0.42, vRadiusFrac));
 normalCol = mix(normalCol, nOuter, smoothstep(0.42, 1.00, vRadiusFrac));
 float ss = fract((vColor - ${(1.0 - CFG.colorParticleRatio).toFixed(3)}) / ${CFG.colorParticleRatio.toFixed(3)} * 5.0) * 5.0;
 vec3 s0 = uAccentColor * ${CFG.colorLevels.sparkle.toFixed(2)};
 vec3 s1 = mix(uAccentColor, uCoreColor, 0.35) * ${CFG.colorLevels.sparkle.toFixed(2)};
 vec3 s2 = mix(uOuterColor, uCoreColor, 0.2) * ${CFG.colorLevels.sparkle.toFixed(2)};
 vec3 s3 = uOuterColor * ${CFG.colorLevels.sparkle.toFixed(2)};
 vec3 s4 = mix(uAccentColor, uOuterColor, 0.5) * ${CFG.colorLevels.sparkle.toFixed(2)};
 vec3 specialCol;
 if(ss < 1.0) specialCol = mix(s0, s1, ss);
 else if(ss < 2.0) specialCol = mix(s1, s2, ss - 1.0);
 else if(ss < 3.0) specialCol = mix(s2, s3, ss - 2.0);
 else if(ss < 4.0) specialCol = mix(s3, s4, ss - 3.0);
 else specialCol = mix(s4, s0, ss - 4.0);
 intensity = mix(intensity, clamp(intensity * 2.5, 0.0, 1.0), isSpecial);
 vec3 col = mix(normalCol, specialCol, isSpecial);
 float alpha = disc * intensity * 0.90;
 gl_FragColor = vec4(col * alpha, alpha);
}
`
export const SMOKE_VERT = /* glsl */`
precision highp float;
uniform sampler2D uPosition;
uniform float uPixelRatio;
uniform float uTime;
uniform float uParticleSize;
attribute vec2 aRef;
attribute float aRadiusFrac;
attribute float aSeed;
varying float vRadiusFrac;
varying float vPhase;
varying float vSeed;
void main(){
 vec4 posData = texture2D(uPosition, aRef);
 vec3 pos = posData.xyz;
 vPhase = posData.w;
 vRadiusFrac = aRadiusFrac;
 vSeed = aSeed;
 vec4 mvPos = modelViewMatrix * vec4(pos, 1.0);
 float depth = -mvPos.z;
 float sizeFactor = mix(0.6, 1.0, 1.0 - aRadiusFrac);
 float sz = ${SMOKE_CFG.particleSize.toFixed(1)} * uParticleSize * sizeFactor * (0.7 + aSeed * 0.6);
 sz *= (420.0 / max(depth, 0.1)) * uPixelRatio;
 gl_PointSize = clamp(sz, 2.0, ${SMOKE_CFG.particleSize.toFixed(1)} * uParticleSize * 3.0);
 gl_Position = projectionMatrix * mvPos;
}
`
export const SMOKE_FRAG = /* glsl */`
precision highp float;
varying float vRadiusFrac;
varying float vPhase;
varying float vSeed;
uniform vec3 uCoreColor;
uniform vec3 uAccentColor;
uniform vec3 uOuterColor;
void main(){
 vec2 uv = gl_PointCoord - 0.5;
 uv.x *= 2.1;
 uv.y *= 0.72;
 float r = length(uv) * 2.0;
 if(r > 1.0) discard;
 float core = exp(-dot(uv, uv) * 3.4);
 float halo = exp(-dot(uv, uv) * 0.75) * 0.9;
 float shape = clamp(core + halo, 0.0, 1.0);
 float streak = 0.72 + 0.28 * smoothstep(0.42, 0.0, abs(uv.y));
 float radialFade = pow(1.0 - vRadiusFrac, 0.72);
 float coreBright = smoothstep(0.32, 0.0, vRadiusFrac) * 0.22;
 float intensity = clamp(radialFade + coreBright, 0.0, 1.0);
 float flow = 0.88 + 0.12 * sin(vPhase * 6.28318 * 1.0 + vSeed * 8.0);
 intensity *= flow * streak;
 vec3 cCore = uCoreColor * ${SMOKE_CFG.colorLevels.core.toFixed(2)};
 vec3 cCyan = uAccentColor * ${SMOKE_CFG.colorLevels.cyan.toFixed(2)};
 vec3 cMagenta = mix(uAccentColor, uOuterColor, 0.35) * ${SMOKE_CFG.colorLevels.magenta.toFixed(2)};
 vec3 cViolet = mix(uCoreColor, uAccentColor, 0.45) * ${SMOKE_CFG.colorLevels.violet.toFixed(2)};
 vec3 cOuter = uOuterColor * ${SMOKE_CFG.colorLevels.outer.toFixed(2)};
 float colorNoise = fract(vSeed * 13.371 + vRadiusFrac * 2.71);
 vec3 col = mix(cCore, cCyan, smoothstep(0.00, 0.28, vRadiusFrac));
 col = mix(col, cMagenta, smoothstep(0.18, 0.52, vRadiusFrac + (colorNoise - 0.5) * 0.18));
 col = mix(col, cViolet, smoothstep(0.42, 0.78, vRadiusFrac + (colorNoise - 0.5) * 0.22));
 col = mix(col, cOuter, smoothstep(0.72, 1.00, vRadiusFrac));
 float cyanMix = smoothstep(0.15, 0.85, sin(vSeed * 19.0 + vRadiusFrac * 11.0) * 0.5 + 0.5);
 float magentaMix = smoothstep(0.2, 0.9, cos(vSeed * 23.0 - vRadiusFrac * 8.0) * 0.5 + 0.5);
 col = mix(col, cCyan, cyanMix * 0.18);
 col = mix(col, cMagenta, magentaMix * 0.22);
 float alpha = shape * intensity * ${SMOKE_CFG.opacity.toFixed(3)};
 gl_FragColor = vec4(col * alpha, alpha);
}
`
