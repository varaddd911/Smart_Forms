from models import LeaveRequest


def submit_leave_request(leave_request: LeaveRequest) -> str:
    print("\n--- Leave Request Submitted ---")
    print(f"Employee: {leave_request.employee_name}")
    print(f"Employee ID: {leave_request.employee_id}")
    print(f"Leave Type: {leave_request.leave_type}")
    print(f"Start Date: {leave_request.start_date}")
    print(f"End Date: {leave_request.end_date}")
    print(f"Reason: {leave_request.reason}")

    return "Leave request submitted successfully."