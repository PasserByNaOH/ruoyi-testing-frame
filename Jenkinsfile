pipeline {
    agent {
        node {
            label 'built-in'
            customWorkspace '/var/lib/jenkins/ruoyi-testing-frame'
        }
    }

    options {
        skipDefaultCheckout()  // 禁止自动 SCM checkout，项目已在 customWorkspace 中
    }

    environment {
        JAVA_TOOL_OPTIONS = '-Dfile.encoding=UTF-8'
        // 钉钉机器人 Webhook URL（Jenkins → Manage Jenkins → Credentials → Secret text）
        // ID: dingtalk-webhook
        DINGTALK_WEBHOOK = credentials('dingtalk-webhook')
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
        success {
            script {
                try {
                    def text = [
                        '### ✅ 若依测试框架 - 构建成功',
                        '',
                        '> 83 条用例全量通过',
                        '',
                        "| 项目 | 内容 |",
                        "|------|------|",
                        "| 构建编号 | #${env.BUILD_NUMBER} |",
                        "| 耗时 | ${currentBuild.durationString} |",
                        "| 分支 | ${env.GIT_BRANCH ?: 'master'} |",
                        "| [Allure 报告](${env.BUILD_URL}allure) | 点击查看 |",
                        "| [控制台日志](${env.BUILD_URL}console) | 点击查看 |",
                    ].join('\n')

                    def payload = groovy.json.JsonOutput.toJson([
                        msgtype: 'markdown',
                        markdown: [title: "✅ 构建成功 - #${env.BUILD_NUMBER}", text: text]
                    ])

                    writeFile file: '/tmp/dingtalk.json', text: payload
                    sh 'curl -s -X POST -H "Content-Type: application/json" -d @/tmp/dingtalk.json ${DINGTALK_WEBHOOK}'
                } catch (Exception e) {
                    echo "钉钉通知发送失败（不影响构建结果）: ${e.message}"
                }
            }
        }
        failure {
            script {
                try {
                    def text = [
                        '### ❌ 若依测试框架 - 构建失败',
                        '',
                        "> 当前状态: **${currentBuild.result ?: 'FAILURE'}**",
                        '',
                        "| 项目 | 内容 |",
                        "|------|------|",
                        "| 构建编号 | #${env.BUILD_NUMBER} |",
                        "| 耗时 | ${currentBuild.durationString} |",
                        "| 分支 | ${env.GIT_BRANCH ?: 'master'} |",
                        "| [错误日志](${env.BUILD_URL}console) | 点击查看 |",
                        "| [Allure 报告](${env.BUILD_URL}allure) | 部分结果 |",
                    ].join('\n')

                    def payload = groovy.json.JsonOutput.toJson([
                        msgtype: 'markdown',
                        markdown: [title: "❌ 构建失败 - #${env.BUILD_NUMBER}", text: text]
                    ])

                    writeFile file: '/tmp/dingtalk.json', text: payload
                    sh 'curl -s -X POST -H "Content-Type: application/json" -d @/tmp/dingtalk.json ${DINGTALK_WEBHOOK}'
                } catch (Exception e) {
                    echo "钉钉通知发送失败（不影响构建结果）: ${e.message}"
                }
            }
        }
    }
}
