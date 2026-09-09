pipeline {
    agent any

    options {
        skipDefaultCheckout(true)
        timestamps()
        disableConcurrentBuilds()
        timeout(time: 30, unit: 'MINUTES')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Verify Repository') {
            steps {
                sh 'git log -1 --oneline'
                sh 'test -f docker-compose.yml'
                sh 'test -d service'
                sh 'test -d vue'
                sh 'ls -la'
            }
        }

        stage('Prepare Deployment Environment') {
            steps {
                sh 'test -f /run/secrets/devpilot.env'
                sh 'install -m 600 /run/secrets/devpilot.env .env'
            }
        }

        stage('Docker Environment') {
            steps {
                sh 'docker version'
                sh 'docker compose version'
            }
        }

        stage('Validate Compose') {
            steps {
                sh 'docker compose config --quiet'
            }
        }

        stage('Build Images') {
            steps {
                sh 'docker compose -p devpilot build api web'
            }
        }

        stage('Deploy') {
            steps {
                sh 'docker compose -p devpilot up -d --no-deps api web'
                sh 'docker compose -p devpilot ps api web'
            }
        }

        stage('Health Check') {
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
        }
    }
}
