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
echo ">>> [0/7] 替换 APT 源为清华镜像..."
sudo sed -i "s@http://.*archive.ubuntu.com@https://mirrors.tuna.tsinghua.edu.cn@g" /etc/apt/sources.list
sudo sed -i "s@http://.*security.ubuntu.com@https://mirrors.tuna.tsinghua.edu.cn@g" /etc/apt/sources.list
sudo apt update -y

# ── 1. 系统更新 ──
echo ""
echo ">>> [1/7] 系统更新..."
sudo apt upgrade -y

# ── 2. Java 17 ──
echo ""
echo ">>> [2/7] 安装 Java 17..."
sudo apt install -y openjdk-17-jdk
java -version

# ── 3. Jenkins（官方源，清华无 apt 镜像） ──
echo ""
echo ">>> [3/7] 安装 Jenkins（端口 ${JENKINS_PORT}）..."
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
echo ">>> [4/7] 安装 Git..."
sudo apt install -y git

# ── 5. Miniconda + testframe 环境（清华镜像） ──
echo ""
echo ">>> [5/7] 安装 Miniconda + testframe 环境（清华镜像）..."
wget -q "${TUNA}/anaconda/miniconda/Miniconda3-latest-Linux-x86_64.sh" -O /tmp/miniconda.sh
bash /tmp/miniconda.sh -b -p ~/miniconda3

# 配置 conda 清华镜像源
~/miniconda3/bin/conda config --add channels ${TUNA}/anaconda/pkgs/main/
~/miniconda3/bin/conda config --add channels ${TUNA}/anaconda/pkgs/free/
~/miniconda3/bin/conda config --set show_channel_urls yes

~/miniconda3/bin/conda init bash
source ~/.bashrc

# 创建环境并安装 Python 依赖（pip 用清华镜像）
~/miniconda3/bin/conda create -n testframe python=3.12 -y
~/miniconda3/bin/conda run -n testframe pip install -q \
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

echo "testframe 环境已创建，已安装: pytest allure-pytest paramiko pymysql redis sshtunnel pyyaml requests openpyxl"

# ── 6. Allure（GitHub 无镜像，但文件较小 ~60MB） ──
echo ""
echo ">>> [6/7] 安装 Allure ${ALLURE_VERSION}..."
wget -q "https://github.com/allure-framework/allure2/releases/download/${ALLURE_VERSION}/allure-${ALLURE_VERSION}.tgz" -O /tmp/allure.tgz
sudo tar -xzf /tmp/allure.tgz -C /opt/
sudo ln -sf /opt/allure-${ALLURE_VERSION}/bin/allure /usr/local/bin/allure
allure --version

# ── 7. 克隆项目（GitHub 无镜像，若下载慢可配代理） ──
echo ""
echo ">>> [7/7] 克隆项目..."
cd ~
if [ -d "ruoyi-testing-frame" ]; then
    echo "目录已存在，跳过 clone（git pull 更新）"
    cd ruoyi-testing-frame && git pull
else
    echo "若 GitHub 下载慢，可按 Ctrl+C 中断，手动配代理后重试:"
    echo "  git config --global https.proxy http://宿主机IP:7897"
    git clone ${GITHUB_REPO}
fi

# 创建 config.ini（如果不存在）
if [ ! -f ~/ruoyi-testing-frame/conf/config.ini ]; then
    cp ~/ruoyi-testing-frame/conf/config.example.ini ~/ruoyi-testing-frame/conf/config.ini
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
echo "     conda activate testframe"
echo "     cd ~/ruoyi-testing-frame"
echo "     python -m pytest --collect-only"
echo ""
