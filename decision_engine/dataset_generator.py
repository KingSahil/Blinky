import json
import random
from pathlib import Path

# 5 Target Decision Routes:
# 0: DAEMON_SYSTEM   (App launch, media control, session power, system hotkeys)
# 1: OCR_EXACT       (Verbatim text, button labels, menu items, tabs, quoted strings)
# 2: VISION_SPATIAL  (Spatial layout, numerical indices, relative positioning)
# 3: VISION_VISUAL   (Colors, icons without text, images, sliders, thumbnails)
# 4: HYBRID_CONSENSUS(Ambiguous combinations: text + visual styling)

ROUTES = [
    "DAEMON_SYSTEM",
    "OCR_EXACT",
    "VISION_SPATIAL",
    "VISION_VISUAL",
    "HYBRID_CONSENSUS"
]

# Seed vocabulary matrices for high-entropy synthetic generation

APP_NAMES = [
    "Firefox", "Chrome", "Chromium", "Vivaldi", "Spotify", "VS Code", "Visual Studio Code",
    "Terminal", "Foot", "Alacritty", "Kitty", "Discord", "Telegram", "Slack", "Ferdium",
    "WhatsApp", "VLC", "MPV", "Obsidian", "Heroic Games Launcher", "Steam", "GIMP", "Blender",
    "Inkscape", "LibreOffice Calc", "LibreOffice Writer", "Calculator", "File Manager", "Nautilus",
    "Dolphin", "Thunar", "Settings", "System Monitor", "EasyEffects", "Thunderbird"
]

MEDIA_COMMANDS = [
    "mute audio", "unmute sound", "toggle mute", "pause playback", "resume music",
    "skip to next track", "play previous song", "turn the volume up", "lower the volume",
    "decrease volume by 10 percent", "increase volume", "stop music", "next song",
    "previous track", "toggle play pause", "silence speakers", "raise sound level"
]

SYSTEM_COMMANDS = [
    "lock the screen", "lock workstation", "put computer to sleep", "suspend session",
    "hibernate system", "reboot computer", "restart system", "power off the PC",
    "shut down computer", "turn off workstation", "switch to workspace 2", "open app launcher"
]

TEXT_ELEMENTS = [
    "Artifacts", "Kanban", "Capabilities", "Settings", "Sessions", "New Session", "Chat",
    "Submit", "Cancel", "Confirm", "Delete", "Save", "Save As", "Export", "Import", "Edit",
    "View", "Help", "Tools", "File", "Preferences", "Sign In", "Log In", "Register", "Download",
    "Upload", "Refresh", "Reload", "Retry", "Checkout", "Cart", "Pricing", "Documentation",
    "Read More", "Learn More", "Apply", "Filter", "Sort by Date", "Sort by Price", "Next",
    "Back", "Previous", "Finish", "Done", "Overview", "Dashboard", "Profile", "Account", "Billing",
    "Notifications", "Security", "Privacy Policy", "Terms of Service", "Copy", "Paste", "Cut",
    "Select All", "Undo", "Redo", "Search", "Find in Page", "Bookmark", "History", "Extensions"
]

COLORS = ["blue", "red", "green", "yellow", "orange", "purple", "white", "black", "grey", "dark", "light"]

ICONS = [
    "magnifying glass", "gear icon", "three vertical dots", "hamburger menu", "trash can",
    "pencil icon", "plus icon", "minus icon", "check mark", "cross icon", "heart icon",
    "star icon", "bell icon", "user avatar", "profile picture", "camera icon", "microphone icon",
    "speaker icon", "folder icon", "file icon", "link icon", "copy icon", "refresh arrow",
    "play triangle", "pause bars", "forward arrow", "back arrow", "home icon", "shopping cart"
]

SPATIAL_TERMS = [
    "first", "second", "third", "fourth", "fifth", "last", "second to last",
    "top-left", "top-right", "bottom-left", "bottom-right", "in the upper section",
    "at the very bottom", "on the top header", "in the sidebar", "in the center",
    "directly above", "directly below", "to the left of", "to the right of", "next to",
    "beside", "underneath", "adjacent to", "middle one", "rightmost", "leftmost",
    "topmost item", "bottom item"
]

def generate_daemon_system():
    patterns = [
        lambda: f"Launch {random.choice(APP_NAMES)}",
        lambda: f"Open {random.choice(APP_NAMES)}",
        lambda: f"Start {random.choice(APP_NAMES)} application",
        lambda: f"Can you open {random.choice(APP_NAMES)} for me?",
        lambda: f"Bring up {random.choice(APP_NAMES)}",
        lambda: random.choice(MEDIA_COMMANDS).capitalize(),
        lambda: f"Please {random.choice(MEDIA_COMMANDS)}",
        lambda: random.choice(SYSTEM_COMMANDS).capitalize(),
        lambda: f"Could you {random.choice(SYSTEM_COMMANDS)}?",
    ]
    return random.choice(patterns)()

def generate_ocr_exact():
    elem = random.choice(TEXT_ELEMENTS)
    patterns = [
        lambda: f"Click '{elem}'",
        lambda: f"Click on {elem}",
        lambda: f"Select '{elem}'",
        lambda: f"Press the '{elem}' button",
        lambda: f"Tap on '{elem}'",
        lambda: f"Click the text that says '{elem}'",
        lambda: f"Hit '{elem}'",
        lambda: f"Click the '{elem}' tab",
        lambda: f"Navigate to '{elem}'",
        lambda: f"Open the '{elem}' menu",
        lambda: f"Find and click '{elem}'",
        lambda: f"Click link '{elem}'",
        lambda: f"Choose the option '{elem}'",
    ]
    return random.choice(patterns)()

def generate_vision_spatial():
    spatial = random.choice(SPATIAL_TERMS)
    item_types = ["video", "card", "thumbnail", "result", "item", "row", "checkbox", "button", "link", "image", "box"]
    item = random.choice(item_types)
    patterns = [
        lambda: f"Click the {spatial} {item}",
        lambda: f"Select the {spatial} {item} in the list",
        lambda: f"Tap on the {item} {spatial}",
        lambda: f"Click on the {item} located {spatial}",
        lambda: f"Check the {spatial} checkbox",
        lambda: f"Click the {item} {spatial} the search bar",
        lambda: f"Choose the {spatial} option in the dropdown",
        lambda: f"Click the {spatial} element on the screen",
    ]
    return random.choice(patterns)()

def generate_vision_visual():
    color = random.choice(COLORS)
    icon = random.choice(ICONS)
    patterns = [
        lambda: f"Click the {color} button",
        lambda: f"Click on the {icon}",
        lambda: f"Tap the {color} {icon}",
        lambda: f"Click the {icon} in the top corner",
        lambda: f"Select the {color} banner",
        lambda: f"Click the user profile image with the {color} border",
        lambda: f"Hit the {icon} button",
        lambda: f"Click the floating {color} circle",
        lambda: f"Click the video thumbnail showing the desert",
        lambda: f"Click the avatar icon",
        lambda: f"Drag the volume slider thumb",
    ]
    return random.choice(patterns)()

def generate_hybrid_consensus():
    elem = random.choice(TEXT_ELEMENTS)
    color = random.choice(COLORS)
    spatial = random.choice(SPATIAL_TERMS)
    patterns = [
        lambda: f"Click the {color} '{elem}' button",
        lambda: f"Click the '{elem}' button on the {spatial}",
        lambda: f"Select the {color} '{elem}' tab {spatial}",
        lambda: f"Click the {spatial} button labeled '{elem}'",
        lambda: f"Hit the {color} '{elem}' link {spatial}",
        lambda: f"Click the '{elem}' option highlighted in {color}",
    ]
    return random.choice(patterns)()

# Hard Negatives / Adversarial Pair Generation
def generate_hard_negatives():
    adversarial_pairs = [
        # Looks like color, but is a proper text noun -> OCR_EXACT
        ("Click on 'Red Hat Enterprise Linux'", "OCR_EXACT"),
        ("Click 'Blue Jeans Network'", "OCR_EXACT"),
        ("Select the option 'Black Friday Deals'", "OCR_EXACT"),
        ("Click 'Orange Money'", "OCR_EXACT"),
        ("Click 'Green Card Application'", "OCR_EXACT"),
        
        # Color styling -> VISION_VISUAL
        ("Click the red button", "VISION_VISUAL"),
        ("Click the blue icon", "VISION_VISUAL"),
        ("Select the green badge", "VISION_VISUAL"),
        
        # Looks like spatial, but is a literal button label -> OCR_EXACT
        ("Click 'Next'", "OCR_EXACT"),
        ("Click 'Previous Step'", "OCR_EXACT"),
        ("Click 'Back to Top'", "OCR_EXACT"),
        ("Click 'Left Wing Politics'", "OCR_EXACT"),
        
        # Spatial arrangement -> VISION_SPATIAL
        ("Click the button next to the search box", "VISION_SPATIAL"),
        ("Click the link below the title", "VISION_SPATIAL"),
        ("Click the icon to the left of the username", "VISION_SPATIAL"),
        
        # System command with app name vs clicking app text on screen
        ("Open Spotify", "DAEMON_SYSTEM"),
        ("Launch Firefox", "DAEMON_SYSTEM"),
        ("Click the word 'Spotify' in the playlist", "OCR_EXACT"),
        ("Click the link labeled 'Firefox' on the download page", "OCR_EXACT"),
        
        # Sound control vs text matching
        ("Mute audio", "DAEMON_SYSTEM"),
        ("Turn volume up", "DAEMON_SYSTEM"),
        ("Click 'Mute' in the video player controls", "OCR_EXACT"),
        ("Click the speaker icon with the slash", "VISION_VISUAL")
    ]
    return random.choice(adversarial_pairs)

def build_dataset(total_samples=3000):
    dataset = []
    
    generators = [
        (generate_daemon_system, "DAEMON_SYSTEM", 0.18),
        (generate_ocr_exact, "OCR_EXACT", 0.32),
        (generate_vision_spatial, "VISION_SPATIAL", 0.20),
        (generate_vision_visual, "VISION_VISUAL", 0.18),
        (generate_hybrid_consensus, "HYBRID_CONSENSUS", 0.12),
    ]

    for gen_fn, label, weight in generators:
        count = int(total_samples * weight)
        for _ in range(count):
            prompt = gen_fn()
            dataset.append({"text": prompt, "label": label})

    # Add 200 hard negatives
    for _ in range(250):
        prompt, label = generate_hard_negatives()
        dataset.append({"text": prompt, "label": label})

    random.seed(42)
    random.shuffle(dataset)

    # Split: 80% train, 20% validation
    split_idx = int(len(dataset) * 0.8)
    train_data = dataset[:split_idx]
    val_data = dataset[split_idx:]

    return train_data, val_data

def main():
    out_dir = Path("/home/fev/GitRepos/Blinky/decision_engine/data")
    out_dir.mkdir(parents=True, exist_ok=True)

    train_data, val_data = build_dataset(3000)

    train_path = out_dir / "train.jsonl"
    val_path = out_dir / "val.jsonl"

    with open(train_path, "w", encoding="utf-8") as f:
        for item in train_data:
            f.write(json.dumps(item) + "\n")

    with open(val_path, "w", encoding="utf-8") as f:
        for item in val_data:
            f.write(json.dumps(item) + "\n")

    print(f"Generated {len(train_data)} training samples -> {train_path}")
    print(f"Generated {len(val_data)} validation samples -> {val_path}")

    # Class distribution report
    from collections import Counter
    train_dist = Counter(d["label"] for d in train_data)
    print("\nTraining Set Class Distribution:")
    for k, v in train_dist.items():
        print(f"  {k:20s}: {v:4d} ({v/len(train_data)*100:.1f}%)")

if __name__ == "__main__":
    main()
