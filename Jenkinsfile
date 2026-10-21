// AcmeBank AI security pipeline (Linux Jenkins agent).
//
// Every push to main:  test -> train + evaluate model -> build images ->
// deploy CANDIDATE (port 9000) -> attack it (red-team) + UI tests (Selenium) ->
// only if everything passed: deploy the same images to PRODUCTION (port 8000).
// If anything fails, production is not touched and the dashboard (port 8090)
// shows why the deployment was stopped.
pipeline {
    // This project uses the local Linux node; no custom Jenkins label is needed.
    agent any

    triggers {
        pollSCM('H/2 * * * *')          // check GitHub for new commits every 2 minutes
    }

    options {
        disableConcurrentBuilds()       // one deployment at a time
        timeout(time: 60, unit: 'MINUTES')
    }

    environment {
        PATH = "/usr/local/bin:${env.PATH}"
        IMAGE_TAG = "build-${env.BUILD_NUMBER}"   // Docker image tag for this build
        PY = '.venv/bin/python'                  // Python inside the workspace venv
    }

    stages {
        stage('Check Linux prerequisites') {
            steps {
                sh 'rm -rf reports'
                sh 'PATH=/usr/local/bin:$PATH bash pipeline/check-linux.sh'
            }
        }

        stage('Setup') {
            steps {
                sh 'python3 -m venv .venv'
                sh '"$PY" -m pip install -q -r target-app/requirements.txt -r guardrail/requirements.txt -r redteam/requirements.txt'
                dir('selenium-tests') {
                    sh 'npm ci'
                }
                // The dashboard runs all the time; this only (re)starts it if needed.
                sh 'docker compose -p acme-dashboard up -d --build dashboard'
            }
        }

        stage('Unit tests') {
            steps {
                sh '"$PY" -m pytest --junitxml=reports/unit-tests.xml'
            }
        }

        stage('Train model') {
            steps {
                sh '"$PY" -m guardrail.train'
            }
        }

        stage('Evaluate model (quality gate)') {
            steps {
                // exit code 1 = model is not good enough -> pipeline stops here
                sh '"$PY" -m guardrail.evaluate --report reports/model-eval.json'
            }
        }

        stage('Build Docker images') {
            steps {
                sh 'docker compose build'
            }
        }

        stage('Deploy candidate') {
            steps {
                withEnv(['CHATBOT_PORT=9000']) {
                    sh 'docker compose -p acme-candidate up -d --wait --no-build'
                }
            }
        }

        stage('Warm up LLM') {
            steps {
                // load qwen2.5:3b into memory so the first test does not time out
                sh '"$PY" pipeline/warmup.py'
            }
        }

        // catchError: mark the stage and build as failed but keep going, so the
        // Selenium tests still run and the dashboard gets every reason.
        stage('Red-team security tests') {
            steps {
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    sh '"$PY" -m redteam.runner --target http://127.0.0.1:9000 --report-dir reports/redteam'
                }
            }
        }

        stage('Selenium UI tests') {
            steps {
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    dir('selenium-tests') {
                        withEnv(['BASE_URL=http://127.0.0.1:9000']) {
                            sh 'npm run test:ci'
                        }
                    }
                }
            }
        }

        stage('Deploy to production') {
            when {
                expression { currentBuild.currentResult == 'SUCCESS' }   // every gate passed
            }
            steps {
                withEnv(['CHATBOT_PORT=8000']) {
                    sh 'docker compose -p acme-prod up -d --wait --no-build'
                }
                sh 'curl -sf http://127.0.0.1:8000/health'    // smoke test
            }
        }
    }

    post {
        always {
            sh(returnStatus: true, script: 'docker compose -p acme-candidate down')
            junit allowEmptyResults: true, testResults: 'reports/*.xml'
            archiveArtifacts allowEmptyArchive: true, artifacts: 'reports/**, guardrail/models/**'
            publishHTML(target: [reportName: 'Red-Team Report', reportDir: 'reports/redteam',
                                 reportFiles: 'report.html', keepAll: true,
                                 alwaysLinkToLastBuild: true, allowMissing: true])
        }
        success {
            sh(returnStatus: true, script: '"$PY" pipeline/notify.py DEPLOYED')
            script { setDescription() }
        }
        failure {
            sh(returnStatus: true, script: '"$PY" pipeline/notify.py BLOCKED')
            script { setDescription() }
        }
    }
}

// Show "DEPLOYED" or "BLOCKED: <first reason>" next to the build number.
def setDescription() {
    if (fileExists('reports/decision.txt')) {
        currentBuild.description = readFile('reports/decision.txt')
    }
}
