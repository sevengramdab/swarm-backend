from marshmallow import Schema, fields
from marshmallow.validate import OneOf

class TodoItemSchema(Schema):
    id = fields.Int(dump_only=True)
    title = fields.Str(required=True)
    description = fields.Str()
    completed = fields.Bool(default=False)

    class Meta:
        ordered = True