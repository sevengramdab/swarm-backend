from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
import os

app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'todo.db')
db = SQLAlchemy(app)

class Todo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    completed = db.Column(db.Boolean, default=False)

@app.route('/todos', methods=['GET'])
def get_all_todos():
    todos = Todo.query.all()
    output = []
    for todo in todos:
        todo_dict = {
            'id': todo.id,
            'title': todo.title,
            'description': todo.description,
            'completed': todo.completed
        }
        output.append(todo_dict)
    return jsonify(output)

@app.route('/todos', methods=['POST'])
def create_todo():
    data = request.get_json()
    if not data:
        return jsonify({"message": "No input data provided"}), 400
    title = data['title']
    description = data['description']
    new_todo = Todo(title=title, description=description)
    db.session.add(new_todo)
    db.session.commit()
    return jsonify({'id': new_todo.id, 'title': new_todo.title, 'description': new_todo.description}), 201

@app.route('/todos/<int:todo_id>', methods=['GET'])
def get_todo(todo_id):
    todo = Todo.query.get(todo_id)
    if todo is None:
        return jsonify({"message": "Todo not found"}), 404
    else:
        output = {
            'id': todo.id,
            'title': todo.title,
            'description': todo.description,
            'completed': todo.completed
        }
        return jsonify(output)

@app.route('/todos/<int:todo_id>', methods=['PUT'])
def update_todo(todo_id):
    todo = Todo.query.get(todo_id)
    if todo is None:
        return jsonify({"message": "Todo not found"}), 404
    data = request.get_json()
    if 'title' in data:
        todo.title = data['title']
    if 'description' in data:
        todo.description = data['description']
    db.session.commit()
    return jsonify({'id': todo.id, 'title': todo.title, 'description': todo.description})

@app.route('/todos/<int:todo_id>', methods=['DELETE'])
def delete_todo(todo_id):
    todo = Todo.query.get(todo_id)
    if todo is None:
        return jsonify({"message": "Todo not found"}), 404
    db.session.delete(todo)
    db.session.commit()
    return jsonify({'message': 'Todo deleted'})

if __name__ == '__main__':
    app.run(debug=True)