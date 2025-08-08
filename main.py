import gradio as gr
import os
import csv
import zipfile
import shutil
import tempfile

# --- Constants ---
OUTPUT_CSV = "annotations.csv"
DEFAULT_LABELS = []
TEMP_AUDIO_DIR = "temp_audio"

def load_directory(path):
    if not path or not os.path.exists(path):
        return []
    return sorted([
        os.path.join(path, f)
        for f in os.listdir(path)
        if f.lower().endswith(('.wav', '.mp3', '.flac', '.ogg', '.m4a'))
    ])


def load_labels_from_fileobj(fileobj):
    if not fileobj:
        return DEFAULT_LABELS
    try:
        with open(fileobj.name, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    except Exception:
        return DEFAULT_LABELS
        
def ensure_readable_audio_path(path):
    """
    Copies the given audio file into a temporary directory managed by tempfile,
    ensuring the file is accessible to Gradio without path issues.
    Returns the new temp file path.
    """
    if not path:
        return None

    path = os.path.abspath(path)
    cwd = os.path.abspath(os.getcwd())

    # If already inside cwd or /tmp, return as is (no copy needed)
    if path.startswith(cwd) or path.startswith(tempfile.gettempdir()):
        return path

    # Copy to a new temp file preserving the extension
    suffix = os.path.splitext(path)[1]
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            shutil.copyfile(path, tmp_file.name)
            return tmp_file.name
    except Exception as e:
        raise RuntimeError(f"Failed to copy audio file to temp directory: {e}")

        
def navigate_files(direction, current_index, file_list):
    if not file_list:
        return 0, None, "No files loaded", ""
    new_index = max(0, min(current_index + direction, len(file_list) - 1))
    original_path=file_list[new_index]
    current_file = file_list[new_index]
    current_file=ensure_readable_audio_path(original_path)
    filename = os.path.basename(original_path)
    status = f"File {new_index+1} / {len(file_list)}"
    return new_index, current_file, status, filename

def save_annotation(current_index, file_list, labels, annotations):
    if not file_list or current_index is None or current_index >= len(file_list):
        return "No file to save", annotations

    current_file = file_list[current_index]
    filename = os.path.basename(current_file)
    annotations = annotations[:] 
    annotations[current_index] = {
        "filename": filename,
        "labels": ", ".join(labels) if labels else ""}
    # persist:
    try:
        with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=["filename", "labels"])
            writer.writeheader()
            for entry in annotations:
                if entry:
                    writer.writerow(entry)
        return f"✅ Saved: {filename}", annotations
    except Exception as e:
        return f"❌ Error saving: {str(e)}", annotations


def load_existing_annotations():
    existing = {}
    if os.path.exists(OUTPUT_CSV):
        try:
            with open(OUTPUT_CSV, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:

                    existing[row['filename']] = row
        except Exception:
            pass
    return existing

def init_annotations(file_list, existing_files):
    annotations = [None] * len(file_list)
    for i, filepath in enumerate(file_list):
        filename = os.path.basename(filepath)
        if filename in existing_files:
            annotations[i] = existing_files[filename]
    return annotations

def get_annotations_table(annotations):
    return [[a["filename"], a["labels"]] for a in annotations if a]

def update_label_choices(label_file_upload):

    label_choices = DEFAULT_LABELS

    if label_file_upload:
        loaded = load_labels_from_fileobj(label_file_upload)
        cleaned = [s.strip() for s in loaded if s and s.strip()]
        if cleaned:
            label_choices = [s.title() for s in cleaned]

    return gr.update(choices=label_choices, value=[])

def handle_load(dir_path):

    path = ""
    if dir_path:
        path = dir_path.strip()
    else:
        path = ""

    files = load_directory(path)
    if not files:
        return (
            [], 0, [], 
            None,  
            "No files found", "",
            "No files loaded", 0,
            []
        )

    existing = load_existing_annotations()
    annots = init_annotations(files, existing)

    index, audio_file, status, filename = navigate_files(0, 0, files)
    selected_labels = []
    if annots and annots[0]:
        selected_labels = [l.strip() for l in annots[0]['labels'].split(',') if l.strip()]

    table = get_annotations_table(annots)

    return (
        files, index, annots,
        audio_file,
        status, filename,
        table
    )

def save_labels(labels, idx, files, ann):
    preview = ", ".join(labels) if labels else ""
    status, updated_ann = save_annotation(idx, files, labels, ann or [])
    table = get_annotations_table(updated_ann)
    return preview, updated_ann, status, table

def navigate(direction, curr_idx, files, ann):
    new_idx, audio_file, status, filename = navigate_files(direction, curr_idx, files)
    selected_labels = []
    if ann and len(ann) > new_idx and ann[new_idx]:
        selected_labels = [l.strip() for l in ann[new_idx]['labels'].split(',') if l.strip()]
    return (
        new_idx,
        audio_file,
        status,
        filename,
        selected_labels,
        ", ".join(selected_labels)
    )

def delete_annotation(idx, files, ann):
    if not files or idx is None or idx >= len(files):
        return "No file selected", ann, "No change", *get_annotation_status(ann or [])
    ann = ann[:]  # copy
    if ann and len(ann) > idx:
        ann[idx] = None
    # persist
    try:
        with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=["filename", "labels"])
            writer.writeheader()
            for entry in ann:
                if entry:
                    writer.writerow(entry)
        status = "✅ Deleted annotation"
    except Exception as e:
        status = f"❌ Error deleting: {e}"
    table = get_annotations_table(ann)
    return status, ann, table

def export_annotations(ann):
    try:
        if ann is None:
            ann = []
        with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=["filename", "labels"])
            writer.writeheader()
            for entry in ann:
                if entry:
                    writer.writerow(entry)
        return OUTPUT_CSV, "✅ Exported CSV"
    except Exception as e:
        return None, f"❌ Error exporting: {e}"


with gr.Blocks(css="""
    .progress-bar input[type=range]::-webkit-slider-thumb { background: #4CAF50; }
    .label-preview { font-size: 14px; color: #333; font-style: italic; margin-top: 4px; }
    .nav-btn { font-size: 18px !important; height: 60px !important; }
""") as demo:
    file_list = gr.State([])
    current_index = gr.State(0)
    annotations = gr.State([])


    with gr.Accordion("📂 Load Audio & Labels", open=True):
        with gr.Row():
            dir_input = gr.Textbox(label="Audio Directory", placeholder="/path/to/audio_folder")
            load_btn = gr.Button("🔄 Load Files", variant="primary")
        with gr.Row():
            label_file_upload = gr.File(label="Upload labels.txt", file_types=['.txt'])
            load_labels_btn = gr.Button("📥 Load Labels")


    with gr.Row():

        with gr.Column(scale=1):
            file_display = gr.Textbox(label="Filename", interactive=False)

            audio = gr.Audio(label="🎵 Listen to Audio", interactive=False, type="filepath")

            with gr.Row():
                button_prev = gr.Button("⏮ Previous", variant="secondary", elem_classes=["nav-btn"])
                button_next = gr.Button("Next ⏭", variant="secondary", elem_classes=["nav-btn"])

            labels_component = gr.CheckboxGroup(
                label="Labels",
                choices=[]
            )
            label_preview = gr.Markdown("*(No labels selected)*", elem_classes=["label-preview"])

            save_btn = gr.Button("💾 Save Labels", variant="primary")


        with gr.Column(scale=1):
            file_status = gr.Textbox(label="File Status", interactive=False)
            annotation_table = gr.Dataframe(
    		headers=["filename", "labels"],
    		value=[],
    		interactive=False,
    		wrap=True
		)

            with gr.Row():
                delete_btn = gr.Button("🗑 Delete Annotation", variant="stop")
                export_btn = gr.Button("📤 Export CSV", variant="primary")
            export_file = gr.File(label="Download CSV", interactive=False)


    load_labels_btn.click(
        fn=update_label_choices,
        inputs=[label_file_upload],
        outputs=[labels_component]
    )

    load_btn.click(
        fn=handle_load,
        inputs=[dir_input],
        outputs=[
            file_list, current_index, annotations,
            audio, file_status, file_display,
            annotation_table
        ]
    )

    save_btn.click(
        fn=save_labels,
        inputs=[labels_component, current_index, file_list, annotations],
        outputs=[label_preview, annotations, file_status, annotation_table]
    )

    button_prev.click(
        fn=lambda idx, files, ann: navigate(-1, idx, files, ann),
        inputs=[current_index, file_list, annotations],
        outputs=[current_index, audio, file_status, file_display, labels_component, label_preview]
    )

    button_next.click(
        fn=lambda idx, files, ann: navigate(1, idx, files, ann),
        inputs=[current_index, file_list, annotations],
        outputs=[current_index, audio, file_status, file_display, labels_component, label_preview]
    )

    labels_component.change(
        fn=lambda labels: ", ".join(labels) if labels else "*(No labels selected)*",
        inputs=labels_component,
        outputs=label_preview
    )

    delete_btn.click(
        fn=lambda idx, files, ann: delete_annotation(idx, files, ann),
        inputs=[current_index, file_list, annotations],
        outputs=[file_status, annotations, annotation_table]
    )

    export_btn.click(
        fn=lambda ann: export_annotations(ann),
        inputs=[annotations],
        outputs=[export_file, file_status]
    )

if __name__ == "__main__":
    demo.launch()


