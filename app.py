from conversation import ConversationState
from flow import describe_changes, process_turn
from prompts import FIELD_LABELS, QUESTIONS


def main():
    state = ConversationState()
    awaiting = None

    print("Smart Forms leave assistant. Describe your leave request.")
    print("Type 'quit' to exit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue

        if user_input.lower() in {"quit", "exit"}:
            break

        result = process_turn(state, user_input, awaiting)
        awaiting = result.next_field

        if result.error:
            print(f"Assistant: Sorry, {result.error}.")
        elif result.submitted:
            print("\nAssistant: That is submitted. Start another request or type 'quit'.")
        elif result.changed:
            print(f"Assistant: Got {describe_changes(result.changed, result.values)}.")
        elif result.unrecognised:
            label = FIELD_LABELS[result.unrecognised].lower()
            print(f"Assistant: That does not look like a {label}.")
        else:
            print("Assistant: I did not catch any new details there.")

        if awaiting:
            print(f"Assistant: {QUESTIONS[awaiting]}")

        print()


if __name__ == "__main__":
    main()
