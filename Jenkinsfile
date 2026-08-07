pipeline {
    agent any

    environment {
        JAVA_TOOL_OPTIONS = '-Dfile.encoding=UTF-8'
    }

    stages {

        // ── 0. 准备环境 ──
        stage('0. 环境准备') {
            steps {
                sh '''
                    # 若项目目录已存在，只做 git pull
                    if [ -d /home/aaa/ruoyi-testing-frame ]; then
                        cd /home/aaa/ruoyi-testing-frame && git pull
                    else
                        git clone https://github.com/PasserByNaOH/ruoyi-testing-frame.git /home/aaa/ruoyi-testing-frame
                    fi
                '''
            }
        }

        // ── 1. 登录测试 ──
        stage('1. 登录测试') {
            steps {
                sh '''
                    cd /home/aaa/ruoyi-testing-frame
                    uv run pytest test_runner/test_login/ \
                        --alluredir=report/temp \
                        --clean-alluredir \
                        -v
                '''
            }
        }

        // TODO: Stage 2 ~ 4 后续逐步添加

    }

    post {
        always {
            sh '''
                cd /home/aaa/ruoyi-testing-frame
                allure generate report/temp -o report/allure --clean
            '''
            archiveArtifacts artifacts: '/home/aaa/ruoyi-testing-frame/report/allure/**', allowEmptyArchive: true
        }
    }
}
