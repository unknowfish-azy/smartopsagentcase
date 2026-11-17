// 遥控能力模型测试：钉死「按能力清单渲染、不按设备类型写分支」的口径。
// 关键约束：不支持的轴必须钳到 0 并如实回报，绝不能猜一个"合理值"。

import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildMoveParams,
  createCommandPacer,
  createCommandSequence,
  isIdleIntent,
  mapJoystickToAxes,
  resolveTeleopProfile,
  TELEOP_AXES,
  TELEOP_INTERVAL_MS,
  TELEOP_PROFILES
} from '../src/utils/teleopCapabilities.js'

test('四类设备的能力清单差异与轴命名一致', () => {
  assert.deepEqual([...TELEOP_PROFILES.CAR.axes], ['forward', 'yaw'])
  assert.deepEqual([...TELEOP_PROFILES.DOG.axes], ['forward', 'lateral', 'yaw', 'gait'])
  assert.deepEqual([...TELEOP_PROFILES.SPIDER.axes], ['forward', 'lateral', 'yaw'])
  assert.deepEqual([...TELEOP_PROFILES.ROBOT.axes], ['forward', 'yaw'])
  // 只有四足有步态档位
  assert.deepEqual([...TELEOP_PROFILES.DOG.gaits], ['TROT', 'WALK', 'STAND'])
  assert.equal(TELEOP_PROFILES.CAR.gaits.length, 0)
  // 四足限速必须低于巡逻车，避免"狗跑得比车快"这种能力表错误
  assert.ok(TELEOP_PROFILES.DOG.maxSpeed.linear < TELEOP_PROFILES.CAR.maxSpeed.linear)
  for (const profile of Object.values(TELEOP_PROFILES)) {
    for (const axis of profile.axes) {
      assert.ok(TELEOP_AXES.includes(axis), `${profile.formFactor} 声明了未登记轴 ${axis}`)
    }
  }
})

test('差速车摇杆左右映射为自转，不会偷偷产生横移', () => {
  const profile = resolveTeleopProfile({ deviceKey: 'car-1', formFactor: 'CAR', capabilities: ['MOVE'] })
  const mapped = mapJoystickToAxes(profile, { x: 0.8, y: 0.5 })
  assert.deepEqual(mapped, { forward: 0.5, lateral: 0, yaw: 0.8 })

  const { params, unsupportedAxes } = buildMoveParams(profile, { ...mapped, lateral: 0 })
  assert.deepEqual(params, { x: 0.5, y: 0, theta: 0.8, speed: 0.6, ttlMs: 200 })
  assert.deepEqual(unsupportedAxes, [])
})

test('四足摇杆左右映射为横移，自转交给独立左右键', () => {
  const profile = resolveTeleopProfile({ deviceKey: 'dog-1', formFactor: 'DOG', capabilities: ['MOVE'] })
  const mapped = mapJoystickToAxes(profile, { x: 0.8, y: 0.5 })
  assert.deepEqual(mapped, { forward: 0.5, lateral: 0.8, yaw: 0 })

  const { params } = buildMoveParams(profile, { ...mapped, yaw: -1 }, { gait: 'WALK' })
  assert.deepEqual(params, { x: 0.5, y: 0.8, theta: -1, speed: 0.35, ttlMs: 200, gait: 'WALK' })
})

test('全向蜘蛛三轴独立，且不携带步态字段', () => {
  const profile = resolveTeleopProfile({ deviceKey: 'spider-1', formFactor: 'SPIDER', capabilities: ['MOVE'] })
  const { params } = buildMoveParams(profile, { forward: 1, lateral: -1, yaw: 0.4 })
  assert.deepEqual(params, { x: 1, y: -1, theta: 0.4, speed: 0.45, ttlMs: 200 })
  assert.equal('gait' in params, false, '无 gait 轴的形态不应出现该字段')
})

test('不支持轴被钳到 0 并如实回报，而不是静默丢弃', () => {
  const car = resolveTeleopProfile({ deviceKey: 'car-1', formFactor: 'CAR', capabilities: ['MOVE'] })
  const { params, unsupportedAxes } = buildMoveParams(car, { forward: 1, lateral: 0.7 })
  assert.equal(params.y, 0, '差速车横移必须为 0')
  assert.deepEqual(unsupportedAxes, ['lateral'])
})

test('步态只接受白名单值，非法值回落首个合法档位', () => {
  const dog = resolveTeleopProfile({ deviceKey: 'dog-1', formFactor: 'DOG', capabilities: ['MOVE'] })
  assert.equal(buildMoveParams(dog, { forward: 1 }, { gait: 'FLY' }).params.gait, 'TROT')
  assert.equal(buildMoveParams(dog, { forward: 1 }, { gait: 'stand' }).params.gait, 'TROT', '大小写不匹配即视为非法')
  assert.equal(buildMoveParams(dog, { forward: 1 }, { gait: 'STAND' }).params.gait, 'STAND')
})

test('速度默认取能力表限速，显式传值按 0~1 钳位', () => {
  const dog = resolveTeleopProfile({ deviceKey: 'dog-1', formFactor: 'DOG', capabilities: ['MOVE'] })
  assert.equal(buildMoveParams(dog, { forward: 1 }).params.speed, 0.35)
  assert.equal(buildMoveParams(dog, { forward: 1 }, { speed: 2 }).params.speed, 1)
  assert.equal(buildMoveParams(dog, { forward: 1 }, { speed: -1 }).params.speed, 0)
})

test('未登记形态退化为最保守两轴并标记 known=false', () => {
  const profile = resolveTeleopProfile({ deviceKey: 'x-1', formFactor: 'HOVER' })
  assert.equal(profile.known, false)
  assert.deepEqual([...profile.axes], ['forward', 'yaw'])
  assert.equal(profile.teleopCapable, true)
})

test('未声明 MOVE 能力的设备不可遥控（只读占位）', () => {
  const profile = resolveTeleopProfile({ deviceKey: 'h-1', formFactor: 'ROBOT', capabilities: ['CAMERA'] })
  assert.equal(profile.teleopCapable, false)
  assert.match(profile.reason, /MOVE/)
})

test('空设备不抛异常，直接判定不可遥控', () => {
  for (const input of [null, undefined, 42, 'car']) {
    const profile = resolveTeleopProfile(input)
    assert.equal(profile.teleopCapable, false)
    assert.equal(profile.known, false)
  }
})

test('后端下发的 teleop 是权威来源，覆盖本地兜底表', () => {
  const profile = resolveTeleopProfile({
    deviceKey: 'car-2',
    formFactor: 'CAR',
    capabilities: ['MOVE'],
    // 后端把某台车的形态标成全向，前端必须照办而不是"按类型纠正"
    teleop: {
      formFactor: 'CAR',
      label: '改装巡逻车',
      kinematics: 'omnidirectional',
      axes: ['forward', 'lateral', 'yaw'],
      maxSpeed: { linear: 0.5, angular: 0.6 },
      gaits: [],
      maxSpeedNote: '改装全向底盘',
      known: true
    }
  })
  assert.equal(profile.source, 'backend')
  assert.equal(profile.label, '改装巡逻车')
  assert.deepEqual(profile.axes, ['forward', 'lateral', 'yaw'])
  assert.equal(buildMoveParams(profile, { forward: 0, lateral: 1 }).params.y, 1)
})

test('teleop 关键字段不合法时整体弃用，回落本地表并标记来源', () => {
  const broken = [
    { axes: ['lateral'], maxSpeed: { linear: 0.5, angular: 0.5 } },
    { axes: ['forward'], maxSpeed: { linear: 'fast', angular: 0.5 } },
    { axes: ['forward'], maxSpeed: {} },
    'garbage'
  ]
  for (const teleop of broken) {
    const profile = resolveTeleopProfile({ deviceKey: 'dog-2', formFactor: 'DOG', initial: teleop, teleop })
    assert.equal(profile.source, 'local', `应弃用非法 teleop：${JSON.stringify(teleop)}`)
    assert.deepEqual(profile.axes, ['forward', 'lateral', 'yaw', 'gait'])
  }
})

test('后端 teleop 声明 known=false 时如实透传，不假装已登记', () => {
  const profile = resolveTeleopProfile({
    deviceKey: 'hover-1',
    formFactor: 'HOVER',
    teleop: { formFactor: 'HOVER', axes: ['forward', 'yaw'], maxSpeed: { linear: 0.3, angular: 0.5 }, known: false }
  })
  assert.equal(profile.source, 'backend')
  assert.equal(profile.known, false)
})

test('capabilities 为 JSON 字符串时同样能判定是否可遥控', () => {
  const readonly = resolveTeleopProfile({ deviceKey: 'cam-1', formFactor: 'CAR', capabilities: '["CAMERA"]' })
  assert.equal(readonly.teleopCapable, false)

  const movable = resolveTeleopProfile({ deviceKey: 'car-3', formFactor: 'CAR', capabilities: '["MOVE","PTZ"]' })
  assert.equal(movable.teleopCapable, true)

  const broken = resolveTeleopProfile({ deviceKey: 'car-4', formFactor: 'CAR', capabilities: 'not-json' })
  assert.equal(broken.teleopCapable, true, '无法解析时不臆断为无能力，按未声明处理')
})

test('节流器按 80ms 放行，且不因抖动提前放行', () => {
  assert.equal(TELEOP_INTERVAL_MS, 80)
  const pacer = createCommandPacer(TELEOP_INTERVAL_MS, 1000)
  assert.equal(pacer.allow(1000), true)
  assert.equal(pacer.allow(1050), false)
  assert.equal(pacer.allow(1079), false)
  assert.equal(pacer.allow(1080), true)
  assert.equal(pacer.allow(Number.NaN), false)
})

test('命令序号严格递增，供桥端判乱序', () => {
  const seq = createCommandSequence()
  assert.deepEqual([seq.next(), seq.next(), seq.next()], [1, 2, 3])
  assert.equal(seq.current, 4)
})

test('全零意图判定为松手', () => {
  assert.equal(isIdleIntent({ forward: 0, lateral: 0, yaw: 0 }), true)
  assert.equal(isIdleIntent({}), true)
  assert.equal(isIdleIntent({ yaw: 0.01 }), false)
})
