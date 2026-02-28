# 从 PyBullet 迁移到 Isaac 的训练改造指南

本项目当前是“单环境 + PyBullet + SB3(PPO/SAC)”结构。迁移到 Isaac（建议 Isaac Lab）时，核心思想是：

1. 保留你现有的“任务定义”（观测、动作、奖励、终止）；
2. 把“物理后端接口”从 PyBullet API 替换成 Isaac 的张量化 API；
3. 把训练器从 SB3 单机向量化，升级为 Isaac 常见的大规模并行训练（如 rsl_rl / skrl / rl_games）。

---

## 1. 当前项目耦合点（需要被替换的地方）

### 1.1 环境层直接绑定 PyBullet
- `QuadrupedGymEnv` 在构造中显式创建 `BulletClient`，并在大量逻辑中直接调用 pybullet 接口。你需要把这里替换为 Isaac 的 scene/world 和 tensor state 读取。 
- `is_fallen()` 通过 `getMatrixFromQuaternion` 和 base height 判断摔倒，逻辑可以原样迁移，但数据来源改成 Isaac root state 张量。

### 1.2 机器人封装层依赖 PyBullet 关节/接触 API
- `env/quadruped.py` 封装了 `GetMotorAngles/GetMotorVelocities/GetContactInfo/GetBasePosition` 等接口，但底层是 `getJointState/getContactPoints/getBaseVelocity`。
- 建议保留这层“语义接口”，在 Isaac 里重写 backend（例如 `QuadrupedIsaac`），减少上层任务代码改动。

### 1.3 训练脚本依赖 SB3 与 Gym VecEnv
- `run_sb3.py` 当前使用 `stable_baselines3` + `make_vec_env` + `VecNormalize`。
- Isaac 场景下通常直接用“GPU 并行环境 + GPU RL 算法实现”。可选：
  - 继续 gym 风格对接（改动较小，但并行效率有限）；
  - 或切 Isaac Lab + rsl_rl（推荐，吞吐高）。

### 1.4 配置中有 Bullet 依赖
- `env/configs_a1.py` 使用了 `pybullet.invertTransform` 计算初始姿态逆。
- 该部分可替换成 `scipy` 或自写四元数逆，避免对 pybullet 的硬依赖。

---

## 2. 推荐迁移架构

建议拆成三层，先“后端解耦”，再换引擎：

1. **Task 层**（不依赖引擎）
   - observation 组装
   - reward 函数
   - done/reset 条件

2. **Robot Backend 层**（依赖引擎）
   - `get_joint_pos/vel/torque`
   - `apply_action`
   - `get_base_state`
   - `get_contact_state`

3. **Runner 层**（训练器）
   - SB3 runner（过渡期）
   - Isaac RL runner（最终）

这样可以先做“同一 Task，双后端可切换（PyBullet / Isaac）”，验证一致性后再完全切换。

---

## 3. 分阶段改造路线（可直接执行）

### Phase A：后端解耦（1~2 天）

- 新增抽象接口（例如 `env/robot_backend.py`）：
  - `reset()`, `step_sim(n)`, `get_obs_dict()`, `apply_joint_torque()` ...
- 让 `QuadrupedGymEnv` 只依赖该接口，不直接 import pybullet。
- 先写 `PyBulletBackend` 适配旧逻辑，确保行为不变。

**验收**：`run_cpg.py` 与 `run_sb3.py` 可无行为退化运行。

### Phase B：Isaac Backend 落地（3~7 天）

- 新建 `IsaacBackend`：
  - 加载 A1 资产（URDF 转 USD 或直接可导入格式）；
  - 读取 root state / dof state / contact force 张量；
  - 支持 batched env（N 并行实例）。
- 实现与 `PyBulletBackend` 同名接口，确保上层任务代码尽量复用。

**关键映射**：
- `GetBasePosition/Orientation` -> Isaac root state tensor；
- `GetMotorAngles/Velocities` -> dof pos/vel tensor；
- `GetContactInfo` -> contact force 或 foot sensor 逻辑；
- `ApplyAction` -> dof effort / position target。

### Phase C：训练器切换（2~4 天）

- 保留原 SB3 入口作为 baseline；
- 增加 Isaac 训练入口（例如 `run_isaac_rl.py`）：
  - PPO 超参数改成适合大并发（如更大 rollout、更高 batch）；
  - 归一化迁移到新框架（obs/reward normalization）。

### Phase D：奖励与观测重标定（持续迭代）

由于引擎差异（接触、摩擦、积分器）会导致“同策略不同表现”，需要重标定：
- 奖励项权重（速度、能耗、姿态、偏航）；
- 动作缩放区间（CPG 的 `omega/mu`）；
- PD 增益与控制频率。

---

## 4. 你项目里可直接复用的部分

- `env/hopf_network.py`：纯 numpy CPG，可直接复用。
- `QuadrupedGymEnv` 里的任务逻辑：
  - `_get_observation()` 结构
  - `_reward_fwd_locomotion()` / `_reward_flag_run()` 思路
  - `is_fallen()` 判据
- `env/configs_a1.py` 的关节范围、默认姿态、增益参数（需重新微调）。

---

## 5. 迁移时最容易踩坑的 10 件事

1. **时间步不一致**：当前 env `time_step=0.001, action_repeat=10`，等效控制频率要在 Isaac 对齐。
2. **关节顺序不一致**：A1 joint index 在不同导入链路可能变化，必须建立 index map。
3. **四元数坐标系定义差异**：注意 world/body 坐标与旋转顺序。
4. **接触判定口径变化**：PyBullet 的 `getContactPoints` 与 Isaac 的 contact force 阈值不等价。
5. **动作裁剪与缩放**：`ScaleActionToCPGStateModulations` 的范围必须重新验证。
6. **PD/力矩控制模式差异**：Isaac 中 actuator model 与 Bullet 电机模型不同。
7. **归一化统计失效**：从 `VecNormalize` 迁移后，旧统计量不能直接复用。
8. **随机化注入位置变化**：摩擦、质量、地形随机化建议放到 reset pipeline。
9. **并行 reset 语义**：isaac batched env 下 done env 要局部 reset，不是整批重置。
10. **性能诊断方式变化**：关注 GPU 利用率、sim step/s、policy step/s，而不是单 env fps。

---

## 6. 最小可行迁移（MVP）建议

如果你希望尽快跑通 Isaac 版本：

1. 先只迁移 `FWD_LOCOMOTION + CPG`（最小任务）；
2. 先不做复杂地形（平地）；
3. 先不加 domain randomization；
4. 先验证：
   - 站立稳定
   - 前进速度 > 0
   - 10 秒内不倒
5. 然后再逐步恢复 `LR_COURSE_OBS/LR_COURSE_TASK`。

---

## 7. 与当前代码一一对应的改造清单

- `env/quadruped_gym_env.py`
  - 删除直接 pybullet client 创建逻辑，改为注入 backend
  - `_get_observation()` 改为从 backend 读取批量状态
  - `step()` 中仿真推进改为 backend 的 batched step

- `env/quadruped.py`
  - 拆成 `quadruped_base.py` + `quadruped_pybullet.py` + `quadruped_isaac.py`

- `run_sb3.py`
  - 保留作为 legacy baseline
  - 新增 `run_isaac_rl.py` 使用 Isaac 训练栈

- `env/configs_a1.py`
  - 去掉 `import pybullet as pyb`
  - 四元数逆改通用实现

---

## 8. 建议的执行优先级

1. **先解耦再迁移**，不要直接在现有类里“硬改成 Isaac”。
2. 先做“单环境 Isaac 对齐测试”，再上大规模并行。
3. 每个阶段都做“同 seed、同初始条件”的短回归，确保 reward 与状态统计不漂移过大。

---

## 9. 结论

你的项目“任务逻辑”是可以复用的，真正需要重做的是“仿真后端 + 训练器并行栈”。
最稳妥路线是：

- 先抽象 backend；
- 再落地 Isaac backend；
- 最后迁移训练器并做 reward/控制参数重标定。

这样可以最大化复用现有 CPG 与任务设计，最小化一次性重写风险。
