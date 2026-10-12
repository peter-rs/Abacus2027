# Abacus

# How to install Abacus

## Install WSL Ubuntu (if on Windows)

Download Ubuntu App from Windows Store

## Install packages:

In Ubuntu:

Update Packages:

```sudo apt update```

Install/verify npm is working:

```npm -v```

Install Docker (Follow instructions at: https://docs.docker.com/engine/install/ubuntu/)

## Install Abacus:

```git clone https://github.com/musyslab/Abacus.git```

Enter Github username and personal access token (not password)

Go into frontend folder:

```npm install``` 

Still in the frontend folder, create a file named: ```.env```

Add the following line to that file: ```VITE_API_URL=http://localhost:5000/api```

(Or different URL for Production)

Go back from the frontend folder into the backend folder. Create ```.env.backend``` Enter environment variables.

## Run Abacus

Go up a directory (from the frontend folder) and run:

```docker compose up```

It will take a while to compile the first time, but once it is ready navigate to the URL:

```http://localhost:3000/```

## View the local Abacus Database

Download DBDeaver: https://dbeaver.io/download/

In DBBeaver, connect to: ```localhost:3306```

## Continuous Integration

Every pull request and every push to `main` runs `.github/workflows/ci.yml` on GitHub Actions:

- **Backend tests** – installs `backend/requirements.txt` on Python 3.10 and runs `pytest` (tests live in `backend/tests/`).
- **Frontend build** – `npm install` + `npm run build` on Node 24.
- **Docker build** – builds all four Dockerfiles (`backend/Dockerfile`, `backend/Dockerfile.prod`, `frontend/Dockerfile`, `frontend/Dockerfile.prod`) without pushing.

Run the backend tests locally (Python 3.10+):

```cd backend && pip install -r requirements.txt && pytest```

The tests set dummy values for the required environment variables themselves, so no `.env.backend` is needed.

## Pushing Docker Image to Production:

Get a github personal access token (PAT)

```export CR_PAT=<github personal access token>```

```echo $CR_PAT | docker login ghcr.io -u USERNAME --password-stdin```

```cd into the frontend/backend directory```

```docker build -f Dockerfile.prod -t ghcr.io/musyslab/abacus-<frontend/backend>:v<VERSION_NUMBER> .```

```docker push ghcr.io/musyslab/abacus-<frontend/backend>:v<VERSION_NUMBER>```
