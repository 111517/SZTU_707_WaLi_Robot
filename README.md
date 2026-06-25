# SZTU_707_WaLi_Robot
# 机器人项目代码整理说明

本仓库用于集中整理707团队在不同机器人平台上的项目代码，方便后续查找、复现、维护和交接。

当前主要包含以下方向：

- Unitree Go2 四足机器人
- TurtleBot4 移动机器人
- 机械臂
- 无人机
- 网页端

## 目录结构

```text
.
├── unitree_go2/        # Unitree Go2 相关代码
├── turtlebot4/         # TurtleBot4 相关代码
├── robotic_arm/        # 机械臂相关代码
├── drone/              # 无人机相关代码
├── web/                # 网页端相关代码
├── common/             # 多平台共用代码、工具、配置
├── docs/               # 文档、实验记录、接口说明
├── scripts/            # 常用安装、启动、数据处理脚本
└── README.md           # 总体说明

## 开发人员提交代码流程

所有开发人员不要直接向 `main` 分支提交代码。

每次上传或修改代码时，请先从 `main` 新建自己的分支，完成后提交 Pull Request，由管理员审核后再合并到 `main`。

### 1. 克隆仓库

```bash
git clone https://github.com/111517/SZTU_707_WaLi_Robot.git
cd SZTU_707_WaLi_Robot
```

### 2. 更新 main 分支

```bash
git checkout main
git pull origin main
```

### 3. 新建自己的开发分支

分支命名建议：

```text
import/项目名称
feature/功能名称
fix/修改内容
```

例如：

```bash
git checkout -b import/unitree-go2
```

```bash
git checkout -b import/turtlebot4
```

```bash
git checkout -b import/robotic-arm
```

```bash
git checkout -b import/drone
```

### 4. 将代码放入对应目录

```text
unitree_go2/      # Unitree Go2 相关代码
turtlebot4/       # TurtleBot4 相关代码
robotic_arm/      # 机械臂相关代码
drone/            # 无人机相关代码
web/              # 网页端相关代码
```

请不要把不同平台的代码混在一起。

### 5. 查看修改内容

```bash
git status
```

### 6. 添加并提交代码

```bash
git add .
git commit -m "Add unitree go2 project code"
```

提交信息请简单说明本次提交内容，例如：

```bash
git commit -m "Add turtlebot4 navigation code"
git commit -m "Add robotic arm control demo"
git commit -m "Add drone simulation scripts"
```

### 7. 推送分支到 GitHub

```bash
git push origin import/unitree-go2
```

如果你的分支名不同，请替换成自己的分支名，例如：

```bash
git push origin import/turtlebot4
```

### 8. 创建 Pull Request

推送完成后，打开 GitHub 仓库页面：

```text
https://github.com/111517/SZTU_707_WaLi_Robot
```

点击：

```text
Compare & pull request
```

确认：

```text
base: main
compare: 你的分支
```

填写说明后提交 Pull Request。

### 9. 等待管理员审核并合并

管理员检查无误后，会将代码合并到 `main` 分支。

Pull Request 合并后，本地可以回到 `main` 并更新最新代码：

```bash
git checkout main
git pull origin main
```

## 代码提交规范

1. 不要直接向 `main` 分支提交代码。
2. 每次修改都应新建分支。
3. 每个项目代码必须放到对应目录下。
4. 每个项目目录中建议包含自己的 `README.md`。
5. 不要提交无关缓存文件、临时文件或日志文件。
6. 大文件、模型权重、数据集、bag 文件等不要直接上传到 GitHub。
7. 实机运行相关代码必须说明运行条件、停止方式和安全注意事项。

## 子项目 README 建议

每个子项目目录中建议提供单独的 `README.md`，内容包括：

```markdown
# 项目名称

## 项目简介

说明该项目的用途、运行平台和主要功能。

## 环境依赖

- 操作系统：
- ROS 版本：
- Python 版本：
- SDK 版本：
- 其他依赖：

## 安装方法

说明依赖安装、编译和环境配置步骤。

## 运行方法

说明仿真运行、实机运行和测试命令。

## 文件结构

说明主要目录和文件的作用。

## 注意事项

说明安全风险、硬件限制和已知问题。
```
