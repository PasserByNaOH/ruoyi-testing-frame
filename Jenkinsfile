pipeline {
    agent {
        node {
            label 'built-in'
            customWorkspace '/var/lib/jenkins/ruoyi-testing-frame'
        }
    }

    environment {
        JAVA_TOOL_OPTIONS = '-Dfile.encoding=UTF-8'
    }

    stages {

        stage('1. 登录测试') {
            steps {
                sh '''
                    cd /var/lib/jenkins/ruoyi-testing-frame
                    uv run pytest test_runner/test_login/ \
                        --alluredir=report/temp \
                        --clean-alluredir \
                        -v
                '''
            }
        }

        stage('2. 用户管理') {
            steps {
                sh '''
                    cd /var/lib/jenkins/ruoyi-testing-frame
                    uv run pytest test_runner/test_user/ \
                        --alluredir=report/temp \
                        -v
                '''
            }
        }

        stage('3. 角色权限') {
            steps {
                sh '''
                    cd /var/lib/jenkins/ruoyi-testing-frame
                    uv run pytest test_runner/test_role/ \
                        --alluredir=report/temp \
                        -v
                '''
            }
        }

        stage('4. 文件与业务流') {
            steps {
                sh '''
                    cd /var/lib/jenkins/ruoyi-testing-frame
                    uv run pytest \
                        test_runner/test_user_excel/ \
                        test_runner/test_business/ \
                        --alluredir=report/temp \
                        -v
                '''
            }
        }

    }

    post {
        always {
            allure includeProperties: false, results: [[path: 'report/temp']]
            script {
                def buildResult = currentBuild.result ?: 'SUCCESS'
                echo "构建结果: ${buildResult}"
            }
        }
    }
}
