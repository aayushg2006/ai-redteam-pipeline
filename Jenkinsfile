// AcmeBank AI security pipeline (Windows Jenkins agent, so steps use `bat`).
//
// Every push to main:  test -> train + evaluate model -> build images ->
// deploy CANDIDATE (port 9000) -> attack it (red-team) + UI tests (Selenium) ->
// only if everything passed: deploy the same images to PRODUCTION (port 8000).
// If anything fails, production is not touched and the dashboard (port 8090)
// shows why the deployment was stopped.
pipeline {
    agent any

    triggers {
        pollSCM('H/2 * * * *')          // check GitHub for new commits every 2 minutes
    }

    options {
        disableConcurrentBuilds()       // one deployment at a time
        timeout(time: 60, unit: 'MINUTES')
    }

    environment {
        IMAGE_TAG = "build-${env.BUILD_NUMBER}"   // Docker image tag for this build
        PY = '.venv\\Scripts\\python.exe'         // Python inside the workspace venv
    }

    stages {
        stage('Setup') {
            steps {
                bat 'if exist reports rmdir /s /q reports'
                bat 'py -3.13 -m venv .venv'     // py launcher: always picks Python 3.13
                bat "${PY} -m pip install -q -r target-app/requirements.txt -r guardrail/requirements.txt -r redteam/requirements.txt"
                dir('selenium-tests') {
                    bat 'npm ci'
                }
                // The dashboard runs all the time; this only (re)starts it if needed.
                bat 'docker compose -p acme-dashboard up -d --build dashboard'
            }
        }

        stage('Unit tests') {
            steps {
                bat "${PY} -m pytest --junitxml=reports/unit-tests.xml"
            }
        }

        stage('Train model') {
            steps {
                bat "${PY} -m guardrail.train"
            }
        }

        stage('Evaluate model (quality gate)') {
            steps {
                // exit code 1 = model is not good enough -> pipeline stops here
                bat "${PY} -m guardrail.evaluate --report reports/model-eval.json"
            }
        }

        stage('Build Docker images') {
            steps {
                bat 'docker compose build'
            }
        }

        stage('Deploy candidate') {
            steps {
                withEnv(['CHATBOT_PORT=9000']) {
                    bat 'docker compose -p acme-candidate up -d --wait --no-build'
                }
            }
        }

        // catchError: mark the stage and build as failed but keep going, so the
        // Selenium tests still run and the dashboard gets every reason.
        stage('Red-team security tests') {
            steps {
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    bat "${PY} -m redteam.runner --target http://127.0.0.1:9000 --report-dir reports/redteam"
                }
            }
        }

        stage('Selenium UI tests') {
            steps {
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    dir('selenium-tests') {
                        withEnv(['BASE_URL=http://127.0.0.1:9000']) {
                            bat 'npm run test:ci'
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
                    bat 'docker compose -p acme-prod up -d --wait --no-build'
                }
                bat 'curl -sf http://127.0.0.1:8000/health'    // smoke test
            }
        }
    }

    post {
        always {
            bat 'docker compose -p acme-candidate down'
            junit allowEmptyResults: true, testResults: 'reports/*.xml'
            archiveArtifacts allowEmptyArchive: true, artifacts: 'reports/**, guardrail/models/**'
            publishHTML(target: [reportName: 'Red-Team Report', reportDir: 'reports/redteam',
                                 reportFiles: 'report.html', keepAll: true,
                                 alwaysLinkToLastBuild: true, allowMissing: true])
        }
        success {
            bat(returnStatus: true, script: "${PY} pipeline/notify.py DEPLOYED")
            script { setDescription() }
        }
        failure {
            bat(returnStatus: true, script: "${PY} pipeline/notify.py BLOCKED")
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
