import mammoth
import os
import markdownify

docs_dir = r"e:\Projects\AeroTwin\docs"

for filename in os.listdir(docs_dir):
    if filename.endswith(".docx"):
        docx_path = os.path.join(docs_dir, filename)
        md_filename = filename[:-5] + ".md"
        md_path = os.path.join(docs_dir, md_filename)
        
        # Check if the md file already exists (e.g. Dataset_Model_Collection_Guide.md)
        if not os.path.exists(md_path):
            print(f"Converting {filename} to markdown...")
            with open(docx_path, "rb") as docx_file:
                result = mammoth.convert_to_html(docx_file)
                html = result.value
                md = markdownify.markdownify(html, heading_style="ATX")
                with open(md_path, "w", encoding="utf-8") as md_file:
                    md_file.write(md)
            print(f"Successfully converted to {md_filename}")
        else:
            print(f"Skipping {filename}, {md_filename} already exists.")
