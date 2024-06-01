from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
import sympy as sp

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///school.db'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    is_teacher = db.Column(db.Boolean, default=False)
    students = db.relationship('Student', backref='teacher', lazy=True)
    assignments = db.relationship('Assignment', backref='teacher', lazy=True)


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    answers = db.relationship('Answer', backref='student', lazy=True)
    rating = db.Column(db.Integer, default=0)

    def update_rating(self, correct, late):
        if late:
            self.rating += 100
        elif correct:
            self.rating += 10
        else:
            self.rating -= 5


class Assignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    correct_answer = db.Column(db.String(150), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    answers = db.relationship('Answer', backref='assignment', lazy=True)
    max_attempts = db.Column(db.Integer, nullable=False, default=3)
    deadline = db.Column(db.DateTime, nullable=False)


class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    is_correct = db.Column(db.Boolean, default=False)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignment.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)


class StudentAssignment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignment.id'), nullable=False)
    student = db.relationship('Student', backref=db.backref('student_assignments', cascade='all, delete-orphan'))
    assignment = db.relationship('Assignment', backref=db.backref('student_assignments', cascade='all, delete-orphan'))
    completed = db.Column(db.Boolean, default=False)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/')
@app.route('/index')
def index():
    if current_user.is_authenticated:
        if current_user.is_teacher:
            return redirect(url_for('dashboard'))
    else:
        return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        is_teacher = 'is_teacher' in request.form
        if User.query.filter_by(username=username).first():
            flash('Username already exists', 'danger')
            return redirect(url_for('register'))
        new_user = User(username=username, password=password, is_teacher=is_teacher)
        db.session.add(new_user)
        db.session.commit()
        flash('Account created successfully!', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Login Unsuccessful. Please check username and password', 'danger')
    return render_template('login.html')


@app.route('/dashboard')
@login_required
def dashboard():
    now = datetime.now()
    if current_user.is_teacher:
        students = Student.query.filter_by(teacher_id=current_user.id).all()
        assignments = Assignment.query.filter_by(teacher_id=current_user.id).all()
        return render_template('teacher_dashboard.html', students=students, assignments=assignments, now=now)
    else:
        student_assignments = StudentAssignment.query.filter_by(student_id=current_user.id).all()
        assignments = [sa.assignment for sa in student_assignments]
        student_answers = {
            assignment.id: Answer.query.filter_by(assignment_id=assignment.id, student_id=current_user.id).all() for
            assignment in assignments}
        return render_template('student_dashboard.html', assignments=assignments, student_answers=student_answers,
                               now=now)


@app.route('/add_student', methods=['POST'])
@login_required
def add_student():
    if current_user.is_teacher:
        student_name = request.form.get('student_name')
        student = User.query.filter_by(username=student_name).first()
        if student and student.is_teacher == 0:
            student = Student.query.filter_by(name=student_name).first()
            if student is None:
                student = Student(name=student_name, teacher_id=current_user.id)
                db.session.add(student)
                db.session.commit()
                flash('Student added successfully!', 'success')
            else:
                flash('Student is already in group!', 'danger')
        else:
            flash('Student does not exist, already has a teacher, or is already in your group.', 'danger')
    return redirect(url_for('dashboard'))


@app.route('/create_assignment', methods=['POST'])
@login_required
def create_assignment():
    if current_user.is_teacher:
        content = request.form.get('content')
        correct_answer = request.form.get('correct_answer')
        max_attempts = request.form.get('max_attempts', type=int)
        deadline = datetime.strptime(request.form.get('deadline'), '%Y-%m-%d')
        student_id = request.form.get('student_id', type=int)
        new_assignment = Assignment(content=content, correct_answer=correct_answer, teacher_id=current_user.id,
                                    max_attempts=max_attempts, deadline=deadline)
        db.session.add(new_assignment)
        db.session.commit()
        new_student_assignment = StudentAssignment(student_id=student_id, assignment_id=new_assignment.id)
        db.session.add(new_student_assignment)
        db.session.commit()
        flash('Assignment created and assigned to student successfully!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/submit_answer/<int:assignment_id>', methods=['POST'])
@login_required
def submit_answer(assignment_id):
    if not current_user.is_teacher:
        content = request.form.get('content')
        assignment = Assignment.query.get(assignment_id)
        student_answers = Answer.query.filter_by(assignment_id=assignment_id, student_id=current_user.id).all()
        late_submission = datetime.utcnow() > assignment.deadline

        if len(student_answers) >= assignment.max_attempts:
            flash('You have reached the maximum number of attempts for this assignment.', 'danger')
        elif any(answer.is_correct for answer in student_answers):
            flash('You have already provided a correct answer for this assignment.', 'danger')
        else:
            is_correct = sp.sympify(content) == sp.sympify(assignment.correct_answer)
            new_answer = Answer(content=content, is_correct=is_correct, assignment_id=assignment_id,
                                student_id=current_user.id)
            db.session.add(new_answer)
            db.session.commit()
            Student.query.filter_by(name=current_user.username).first().update_rating(is_correct, late_submission)
            db.session.commit()
            if is_correct:
                flash('Your answer is correct!', 'success')
            else:
                flash('Your answer is incorrect. Please try again.', 'danger')

    return redirect(url_for('dashboard'))


@app.route('/delete_assignment/<int:assignment_id>', methods=['POST'])
@login_required
def delete_assignment(assignment_id):
    if current_user.is_teacher:
        answers = Answer.query.filter_by(assignment_id=assignment_id).all()
        for answer in answers:
            db.session.delete(answer)
        assignment = Assignment.query.filter_by(id=assignment_id).first()
        if assignment:
            db.session.delete(assignment)
            db.session.commit()
            flash('Assignment deleted successfully!', 'success')
        flash('This assignment unexists!', 'danger')
    return redirect(url_for('dashboard'))


@app.route('/view_answers/<int:assignment_id>')
@login_required
def view_answers(assignment_id):
    if current_user.is_teacher:
        assignment = Assignment.query.get(assignment_id)
        answers = Answer.query.filter_by(assignment_id=assignment_id).all()
        return render_template('view_answers.html', assignment=assignment, answers=answers)
    return redirect(url_for('dashboard'))


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
