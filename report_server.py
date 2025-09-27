from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import datetime
import os

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///reports.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)


class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)   # наприклад, "daily_report_2025-09-25"
    content = db.Column(db.Text, nullable=False)       # зберігаємо JSON або CSV
    created_at = db.Column(db.DateTime, default=datetime.datetime.now(datetime.timezone.utc))


def check_is_duplication(name, content) -> bool:
    existing_report = Report.query.filter_by(name=name, content=content).first()
    if existing_report:
        if existing_report.content == content:
            return True
        else:
            return False
    return False

@app.route("/api/reports/upload", methods=["POST"])
def upload_report():
    data = request.get_json()
    if not data or "name" not in data or "content" not in data:
        return jsonify({"error": "Invalid payload"}), 400

    if check_is_duplication(data["name"], data["content"]):
        return jsonify({"message": "Duplicate report"}), 409
    
    report = Report(name=data["name"], content=data["content"])
    db.session.add(report)
    db.session.commit()

    return jsonify({"message": "Report saved", "report_id": report.id})


@app.route("/api/reports", methods=["GET"])
def list_reports():
    reports = Report.query.order_by(Report.created_at.desc()).all()
    return jsonify([
        {
            "id": r.id,
            "name": r.name,
            "created_at": r.created_at.isoformat()
        } for r in reports
    ])


@app.route("/api/reports/<int:report_id>", methods=["GET"])
def get_report(report_id):
    report = Report.query.get_or_404(report_id)
    return jsonify({
        "id": report.id,
        "name": report.name,
        "content": report.content,
        "created_at": report.created_at.isoformat()
    })


if __name__ == "__main__":
    if not os.path.exists("reports.db"):
        with app.app_context():
            db.create_all()
    app.run(host="127.0.0.1", port=5001, debug=True)
