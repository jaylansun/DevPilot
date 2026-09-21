pipeline {
    agent any

    options {
        skipDefaultCheckout(true)
        timestamps()
        disableConcurrentBuilds()
        timeout(time: 30, unit: 'MINUTES')
    }

    stages {
        stage('检出代码') {
            steps {
                checkout scm
            }
        }

        stage('校验代码仓库') {
            steps {
                sh 'git log -1 --oneline'
                sh 'test -f docker-compose.yml'
                sh 'test -d service'
                sh 'test -d vue'
                sh 'ls -la'
            }
        }

        stage('准备部署环境') {
            steps {
                withCredentials([
                    file(
                        credentialsId: 'devpilot-env-file',
                        variable: 'DEVPILOT_ENV_FILE'
                    )
                ]) {
                    sh 'install -m 600 "$DEVPILOT_ENV_FILE" .env'
                }
            }
        }

        stage('检查 Docker 环境') {
            steps {
                sh 'docker version'
                sh 'docker compose version'
            }
        }

        stage('准备构建网络') {
            steps {
                script {
                    env.DOCKER_BUILD_PROXY = sh(
                        script: 'git config --global --get http.proxy || true',
                        returnStdout: true
                    ).trim()
                    if (env.DOCKER_BUILD_PROXY) {
                        echo '已读取 Jenkins Git 代理，镜像构建将使用相同代理'
                    } else {
                        echo '未配置 Jenkins Git 代理，镜像构建将直接访问网络'
                    }
                }
            }
        }

        stage('校验 Compose 配置') {
            steps {
                sh 'docker compose config --quiet'
            }
        }

        stage('后端自动化测试') {
            steps {
                sh '''
                    if [ -n "$DOCKER_BUILD_PROXY" ]; then
                        set -- \
                            --build-arg "HTTP_PROXY=$DOCKER_BUILD_PROXY" \
                            --build-arg "HTTPS_PROXY=$DOCKER_BUILD_PROXY"
                    else
                        set --
                    fi
                    docker build "$@" \
                        --build-context stream_contract=vue/src/types \
                        --target test \
                        --tag "devpilot-api-test:${BUILD_NUMBER}" \
                        service
                '''
                // 测试不读取部署凭据；模型使用替身，数据库使用测试自建的临时库。
                sh '''
                    docker run --rm --network none \
                        -e AI_MODE=mock \
                        -e MODEL_NAME= \
                        -e LLM_API_KEY= \
                        -e LLM_BASE_URL= \
                        -e RAG_MIN_SCORE=0.5 \
                        -e DATABASE_URL=postgresql+psycopg://test:test@127.0.0.1:1/devpilot_test \
                        -e JWT_SECRET=devpilot-test-key-not-for-production \
                        -e LANGSMITH_TRACING=false \
                        -e LANGCHAIN_TRACING_V2=false \
                        devpilot-api-test:${BUILD_NUMBER}
                '''
            }
        }

        stage('构建镜像') {
            steps {
                sh '''
                    if [ -n "$DOCKER_BUILD_PROXY" ]; then
                        set -- \
                            --build-arg "HTTP_PROXY=$DOCKER_BUILD_PROXY" \
                            --build-arg "HTTPS_PROXY=$DOCKER_BUILD_PROXY"
                    else
                        set --
                    fi
                    docker compose -p devpilot build "$@" api web
                '''
            }
        }

        stage('部署服务') {
            steps {
                sh 'docker compose -p devpilot up -d --no-deps api web'
                sh 'docker compose -p devpilot ps api web'
            }
        }

        stage('健康检查') {
            steps {
                sh '''
                    curl --fail --silent --show-error \
                        --retry 15 --retry-delay 2 --retry-connrefused \
                        http://api:8000/api/v1/health
                    curl --fail --silent --show-error \
                        --retry 15 --retry-delay 2 --retry-connrefused \
                        --output /dev/null \
                        http://web/
                '''
            }
        }
    }

    post {
        always {
            sh 'rm -f .env'
            sh 'docker image rm devpilot-api-test:${BUILD_NUMBER} >/dev/null 2>&1 || true'
        }
    }
}
