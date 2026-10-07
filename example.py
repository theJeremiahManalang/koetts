"""The smallest complete example. Run from this project's directory."""
from files import load_image, write_json
from magi import Magi

if __name__ == "__main__":
    # Replace this path with a real comic panel/page before running.
    images = [load_image("images/page1.jpg")]
    # Describe what is actually visible. Grounding locates caption references;
    # it does not create this caption for you.
    captions = ["A girl with glasses talks to a boy wearing a hat."]
    runner = Magi(device="auto")
    result = runner.predict(images, task="all", captions=captions)
    write_json("example-results.json", result)
    print("Saved example-results.json")
