pipeline {
    agent any

    options {
        skipDefaultCheckout(true)
        timestamps()
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
    }
}
