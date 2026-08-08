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

        stage('Clean') {
            steps {
                sh '''
                    cd /var/lib/jenkins/ruoyi-testing-frame
                    rm -rf report/temp
                '''
            }
        }

        stage('Discover & Run') {
            steps {
                script {
                    def modules = sh(
                        script: '''cd /var/lib/jenkins/ruoyi-testing-frame
                                   ls -d test_runner/test_0*/ | sed 's|/$||' | sort''',
                        returnStdout: true
                    ).trim().split('\n')

                    for (module in modules) {
                        def name = module.replaceAll('^test_runner/test_[0-9]+_', '')
                        stage(name) {
                            sh """
                                cd /var/lib/jenkins/ruoyi-testing-frame
                                uv run pytest ${module}/ --alluredir=report/temp -v
                            """
                        }
                    }
                }
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
                        "| Allure 报告| [点击查看](${env.BUILD_URL}allure) |",
                        "| 控制台日志| [点击查看](${env.BUILD_URL}console) |",
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
                        "| 错误日志 | [点击查看](${env.BUILD_URL}console) |",
                        "| Allure 报告 | [部分结果](${env.BUILD_URL}allure) |",
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
