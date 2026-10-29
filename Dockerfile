FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app app
COPY migrations migrations

# Version für die Seitenleiste: Commit aus .git und Baudatum. .git wird nur
# beim Bauen eingebunden, nicht ins Image kopiert, und Git selbst ist nicht nötig.
RUN --mount=type=bind,source=.git,target=/tmp/git python - <<'ENDE'
from datetime import datetime
from pathlib import Path
git = Path("/tmp/git")
head = (git / "HEAD").read_text().strip()
ref = head.removeprefix("ref: ")
if ref == head:
    commit = head
elif (git / ref).exists():
    commit = (git / ref).read_text().strip()
else:
    # Nach git clone oder gc stehen die Refs gesammelt in packed-refs.
    commit = next(z.split()[0] for z in (git / "packed-refs").read_text().splitlines() if z.endswith(" " + ref))
Path("/app/VERSION").write_text(f"{commit[:7]} · gebaut {datetime.now():%d.%m.%Y}")
ENDE

ENV EXPORT_DIR=/exports
ENV DB_PATH=/data/schlagkartei.db

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
