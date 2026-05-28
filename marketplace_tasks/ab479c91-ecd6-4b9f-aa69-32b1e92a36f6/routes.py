from flask import Blueprint, jsonify, request
from models.todo import TodoItem
from db import db

todo_routes = Blueprint('todo_routes', __name__)

@todo_routes.route('/todos', methods=['GET'])
def get_all_todos():
    todos = TodoItem.query.all()
    output = []
    for todo in todos:
        todo_data = {
            'id': todo.id,
            'title': todo.title,
            'description': todo.description
        }
        output.append(todo_data)
    return jsonify(output)

@todo_routes.route('/todos', methods=['POST'])
def create_todo():
    data = request.get_json()
    new_todo = TodoItem(title=data['title'], description=data['description'])
    db.session.add(new_todo)
    db.session.commit()
    return jsonify({'id': new_todo.id, 'title': new_todo.title, 'description': new_todo.description}), 201

@todo_routes.route('/todos/<int:todo_id>', methods=['GET'])
def get_todo(todo_id):
    todo = TodoItem.query.get_or_404(todo_id)
    output = {
        'id': todo.id,
        'title': todo.title,
        'description': todo.description
    }
    return jsonify(output)

@todo_routes.route('/todos/<int:todo_id>', methods=['PUT'])
def update_todo(todo_id):
    todo = TodoItem.query.get_or_404(todo_id)
    data = request.get_json()
    todo.title = data['title']
    todo.description = data['description']
    db.session.commit()
    return jsonify({'id': todo.id, 'title': todo.title, 'description': todo.description})

@todo_routes.route('/todos/<int:todo_id>', methods=['DELETE'])
def delete_todo(todo_id):
    todo = TodoItem.query.get_or_404(todo_id)
    db.session.delete(todo)
    db.session.commit()
    return jsonify({'message': 'Todo item deleted successfully'})