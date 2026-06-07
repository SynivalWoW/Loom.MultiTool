from enum import IntEnum


class M2Offsets(IntEnum):
    # Длина 4 байта
    mdMagic = 0
    nName = 8
    ofsName = 12
    globalFlags = 16
    nGlobalSequences = 20
    ofsGlobalSequences = 24
    nAnimations = 28
    ofsAnimations = 32
    nAnimationLookup = 36
    ofsAnimationLookup = 40
    nBones = 44
    ofsBones = 48
    nVertices = 60
    ofsVertices = 64
    nViews = 68
    nColors = 72
    ofsColors = 76
    pivotPoint = 76
    nTextures = 80
    ofsTextures = 84
    nTransparency = 88
    ofsTransparency = 92
    nTextureAnimations = 96
    ofsTextureAnimations = 100
    nMaterials = 112
    ofsMaterials = 116
    nBoneLookupTable = 120
    ofsBoneLookupTable = 124
    nTexLookup = 128
    ofsTexLookup = 132
    nTransLookup = 144
    ofsTransLookup = 148
    nTexAnimLookup = 152
    ofsTexAnimLookup = 156
    nRibbonEmitters = 288
    ofsRibbonEmitters = 292
    nParticleEmitters = 296
    ofsParticleEmitters = 300
    nTextureCombiner = 304
    ofsTextureCombiner = 308


class M2Lengths(IntEnum):
    material = 4
    pivotPoint = 12
    texture = 16
    transparency = 20
    color = 40
    textureAnimation = 60
    animation = 64
    bone = 88
    particle = 476


class SkinOffsets(IntEnum):
    # WotLK file-based .skin layout (header carries the 'SKIN' magic).
    magic = 0
    nIndices = 4
    ofsIndices = 8
    nTriangles = 12
    ofsTriangles = 16
    nProperties = 20
    ofsProperties = 24
    nSubmeshes = 28
    ofsSubmeshes = 32
    nTextureUnits = 36
    ofsTextureUnits = 40
    nBones = 44


class SkinLengths(IntEnum):
    submesh = 48
    textureUnit = 24


class SkinBatchOffsets(IntEnum):
    # Field offsets inside a single 24-byte texture-unit (M2Batch) record.
    flags = 0
    priorityPlane = 2
    shaderId = 4
    skinSectionIndex = 6
    geosetIndex = 8
    colorIndex = 10
    materialIndex = 12
    materialLayer = 14
    textureCount = 16
    textureComboIndex = 18
    textureCoordComboIndex = 20
    textureWeightComboIndex = 22
