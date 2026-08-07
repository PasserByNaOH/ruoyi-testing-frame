#!/bin/bash
# ============================================================
# ruoyi-testing-frame · Ubuntu 22.04 虚拟机一键部署脚本
# 全部使用清华大学开源镜像源
# 用法: bash setup-vm.sh
# ============================================================
set -e

GITHUB_REPO="https://github.com/PasserByNaOH/ruoyi-testing-frame.git"
ALLURE_VERSION="2.32.0"
JENKINS_PORT=9090
TUNA="https://mirrors.tuna.tsinghua.edu.cn"

echo "=========================================="
echo " 若依测试框架 · VM 环境部署"
echo "（全部镜像源: 清华大学 TUNA）"
echo "=========================================="

# ── 0. 替换 APT 源为清华镜像 ──
echo ""
echo ">>> [0/6] 替换 APT 源为清华镜像..."
sudo sed -i "s@http://.*archive.ubuntu.com@https://mirrors.tuna.tsinghua.edu.cn@g" /etc/apt/sources.list
sudo sed -i "s@http://.*security.ubuntu.com@https://mirrors.tuna.tsinghua.edu.cn@g" /etc/apt/sources.list
sudo apt update -y

# ── 1. 系统更新 ──
echo ""
echo ">>> [1/6] 系统更新..."
sudo apt upgrade -y

# ── 2. Java 17 ──
echo ""
echo ">>> [2/6] 安装 Java 17..."
sudo apt install -y openjdk-17-jdk
java -version

# ── 3. Jenkins（官方源，清华无 apt 镜像） ──
echo ""
echo ">>> [3/6] 安装 Jenkins（端口 ${JENKINS_PORT}）..."
curl -fsSL https://pkg.jenkins.io/debian-stable/jenkins.io-2023.key | sudo tee /usr/share/keyrings/jenkins-keyring.asc > /dev/null
echo "deb [signed-by=/usr/share/keyrings/jenkins-keyring.asc] https://pkg.jenkins.io/debian-stable binary/" | sudo tee /etc/apt/sources.list.d/jenkins.list > /dev/null
sudo apt update -y && sudo apt install -y jenkins

# 修改端口为 9090（避免与云服务器 8080 冲突）
sudo mkdir -p /etc/systemd/system/jenkins.service.d
echo "[Service]
Environment=\"JENKINS_PORT=${JENKINS_PORT}\"" | sudo tee /etc/systemd/system/jenkins.service.d/override.conf > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now jenkins

echo ""
echo "Jenkins 初始密码:"
sudo cat /var/lib/jenkins/secrets/initialAdminPassword

# ── 4. Git ──
echo ""
echo ">>> [4/6] 安装 Git..."
sudo apt install -y git

# ── 5. uv + Python 3.12 + 虚拟环境 ──
echo ""
echo ">>> [5/6] 安装 uv + Python 3.12 + 项目依赖..."
# 安装 uv（官方安装脚本，轻量 ~20MB）
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.cargo/env

# 用 uv 安装 Python 3.12
uv python install 3.12

echo "uv + Python 3.12 已安装"

# ── 5b. 克隆项目 + 创建虚拟环境 + 安装依赖 ──
echo ""
echo ">>> [5b] 克隆项目..."
cd ~
if [ -d "ruoyi-testing-frame" ]; then
    echo "目录已存在，git pull 更新..."
    cd ruoyi-testing-frame && git pull
else
    echo "若 GitHub 下载慢，可按 Ctrl+C 中断，手动配代理后重试:"
    echo "  git config --global https.proxy http://宿主机IP:7897"
    git clone ${GITHUB_REPO}
    cd ruoyi-testing-frame
fi

# 创建虚拟环境 + 安装依赖（pip 用清华镜像）
uv venv --python 3.12
uv pip install \
    -i ${TUNA}/pypi/web/simple \
    --trusted-host mirrors.tuna.tsinghua.edu.cn \
    pytest \
    allure-pytest \
    "paramiko<3.0" \
    pymysql \
    redis \
    sshtunnel \
    pyyaml \
    requests \
    openpyxl

echo ".venv 已创建，已安装: pytest allure-pytest paramiko pymysql redis sshtunnel pyyaml requests openpyxl"

# ── 6. Allure ──
echo ""
echo ">>> [6/6] 安装 Allure ${ALLURE_VERSION}..."
wget -q "https://github.com/allure-framework/allure2/releases/download/${ALLURE_VERSION}/allure-${ALLURE_VERSION}.tgz" -O /tmp/allure.tgz
sudo tar -xzf /tmp/allure.tgz -C /opt/
sudo ln -sf /opt/allure-${ALLURE_VERSION}/bin/allure /usr/local/bin/allure
allure --version

# ── config.ini ──
cd ~/ruoyi-testing-frame
if [ ! -f conf/config.ini ]; then
    cp conf/config.example.ini conf/config.ini
    echo ""
    echo "⚠️  请编辑 ~/ruoyi-testing-frame/conf/config.ini 填入真实密码:"
    echo "   vim ~/ruoyi-testing-frame/conf/config.ini"
fi

# ── 防火墙 ──
if command -v ufw &> /dev/null && sudo ufw status | grep -q "active"; then
    sudo ufw allow ${JENKINS_PORT}
    echo "防火墙已放行 ${JENKINS_PORT}"
fi

# ── 完成 ──
echo ""
echo "=========================================="
echo " 部署完成！"
echo "=========================================="
echo ""
echo "后续步骤:"
echo "  1. 编辑 config.ini: vim ~/ruoyi-testing-frame/conf/config.ini"
echo "  2. Jenkins 初始密码（见上方输出）"
echo "  3. 浏览器访问: http://$(hostname -I | awk '{print $1}'):${JENKINS_PORT}"
echo "  4. 验证环境:"
echo "     cd ~/ruoyi-testing-frame"
echo "     uv run pytest --collect-only"
echo ""
