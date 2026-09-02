from conversation import ConversationState
from flow import describe_changes, process_turn
from llm_service import ConfigurationError, get_client
from prompts import FIELD_LABELS, QUESTIONS


def main():
    try:
        get_client()
    except ConfigurationError as exc:
        print(exc)
        return

    state = ConversationState()
    awaiting = None

    print("SmartIntake. Describe a regulatory query. Type 'quit' to exit.\n")

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

        if result.saved_path:
            print("Assistant: Intake saved successfully.")
            print(f"Assistant: Saved to {result.saved_path}")
        elif result.error:
            print(f"Assistant: Sorry, {result.error}.")
        elif result.out_of_scope:
            print(f"Assistant: {result.fallback_message}")
            if result.confirmation_message:
                print(f"Assistant: {result.confirmation_message}")
        elif result.awaiting_confirmation:
            print(f"\nAssistant: {result.confirmation_message}")
        elif result.changed:
            print(f"Assistant: Got {describe_changes(result.changed, result.values)}.")
        elif result.unrecognised:
            print(f"Assistant: That does not look like a {FIELD_LABELS[result.unrecognised].lower()}.")
        else:
            print("Assistant: I did not catch any new details there.")

        if awaiting and not result.awaiting_confirmation and not result.saved_path:
            print(f"Assistant: {QUESTIONS[awaiting]}")
        elif result.awaiting_confirmation and result.error:
            print(f"Assistant: {result.confirmation_message}")

        print()


if __name__ == "__main__":
    main()
