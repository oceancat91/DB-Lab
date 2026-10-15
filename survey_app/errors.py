"""Errors safe to expose through the application API."""
class DomainError(Exception):
    def __init__(self, status: int, code: str, message: str, question_id: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.question_id = question_id

    def payload(self):
        detail = {'code': self.code, 'message': self.message}
        if self.question_id is not None:
            detail['question_id'] = self.question_id
        return {'error': detail}
