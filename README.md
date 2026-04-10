# CreditSense AI

CreditSense AI is a full-stack Django and AI/ML platform for explainable credit risk scoring. It uses the real dataset stored in `dataset/credit_risk_dataset.csv`, predicts applicant risk with a Random Forest + Logistic Regression ensemble, exposes SHAP/LIME-style explanations, raises fraud alerts, and supports three user roles:

- User (loan applicant)
- Bank Officer
- Admin

## Features

- Session-based registration and login
- Applicant dashboard, profile, prediction history, and improvement suggestions
- Credit scoring workflow using real dataset features only
- Explainable AI outputs with SHAP-compatible and LIME explanations
- Fraud detection based on real-data thresholds and application behavior
- Bank officer review, approval, and rejection workflows
- Admin dashboards for users, fraud, model monitoring, and analytics
- REST APIs for applicant, officer, and admin flows

## Tech Stack

- Backend: Django, Django REST Framework
- AI/ML: scikit-learn, SHAP, LIME
- Frontend: HTML, CSS, JavaScript, Bootstrap
- Database: PostgreSQL via environment variables, SQLite fallback for local development

## Project Structure

- `config/` Django settings and root URLs
- `authentication/` landing page, login, register, logout, login audit
- `users/` applicant model, profile forms, dashboard and history views
- `bank_officer/` officer profile and operational dashboards
- `admin_panel/` admin dashboards and monitoring views
- `credit_prediction/` loan applications, predictions, fraud alerts, workflow services
- `recommendations/` recommendation model, service, and user-facing suggestions
- `analytics/` model monitoring snapshots and system analytics
- `api/` REST endpoints and role-based API permissions
- `ml_engine/` training, prediction, explainability, and fraud services
- `dataset/` real credit risk CSV used for training and reference thresholds
- `templates/` HTML pages for landing, auth, applicant, officer, admin, and analytics
- `static/` shared CSS and JavaScript

## Setup

1. Create or activate a Python 3.10 virtual environment.

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

   Installing into a global interpreter can surface unrelated resolver conflicts from packages already present on the machine.
   This project does not depend on `tensorflow`, `tensorflow-intel`, or `faiss-cpu`, so warnings about those packages mean you are using a mixed interpreter instead of a clean project virtual environment.
   A common example is:

   - `faiss-cpu 1.13.2 requires numpy>=1.25.0`, while this project pins `numpy==1.24.3`
   - `tensorflow-intel 2.13.0 requires typing-extensions<4.6.0`, even though this project does not require TensorFlow at all

   If you see those conflicts, recreate the environment instead of forcing one interpreter to satisfy both stacks.

3. Configure environment variables if you want PostgreSQL:

   - `POSTGRES_DB`
   - `POSTGRES_USER`
   - `POSTGRES_PASSWORD`
   - `POSTGRES_HOST`
   - `POSTGRES_PORT`
   - Optional: `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`

4. Apply migrations:

   ```bash
   python manage.py migrate
   ```

5. Train the model artifacts:

   ```bash
   python ml_engine/prediction_model/train.py
   ```

6. Run the server:

   ```bash
   python manage.py runserver
   ```

## Key Routes

- `/` landing page
- `/login/`, `/register/`
- `/user/dashboard/`
- `/credit/analyze/`
- `/officer/dashboard/`
- `/admin-panel/dashboard/`
- `/api/...` REST endpoints

## Testing

```bash
python manage.py test
```

## Architecture

See `docs/architecture.md` for the system architecture, data flow, database schema, AI pipeline, and deployment notes.
