# Custom exception handler function
import logging
import traceback


def custom_exception_handler(exc_type, exc_value, exc_traceback):
    logging.error("An unhandled exception occurred:", exc_info=(exc_type, exc_value, exc_traceback))
    print("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
# Set the custom exception handler globally

class MissingHoleDataException(Exception):
    def __init__(self, hole_id, message=None):
        self.hole_id = hole_id
        self.message = message
        super().__init__(self.get_exception_message())

    def get_exception_message(self):
        if self.message:
            return f"Missing data for HoleID {self.hole_id}: {self.message}"
        else:
            return f"Missing data for HoleID {self.hole_id}"

