import os
from fpdf import FPDF

def create_pdf_from_text(text_content, person_name, date_obj):
    """
    Creates a PDF report from a string of text and saves it.

    Args:
        text_content (str): The full string content for the report.
        person_name (str): The name of the person for the report title.
        date_obj (datetime.date): The date of the report.

    Returns:
        str: The filename of the generated PDF.
    """
    pdf = FPDF()
    pdf.add_page()
    
    # Set title
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, f"News Report for {person_name}", 0, 1, 'C')
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, f"Date: {date_obj.strftime('%A, %B %d, %Y')}", 0, 1, 'C')
    pdf.ln(10) # Add a little space

    # Set body font
    pdf.set_font('Arial', '', 10)
    
    # Encode the text to handle special characters that FPDF's default fonts might not support
    safe_content = text_content.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 5, safe_content)
    
    # Define filename and save the PDF
    pdf_filename = f"Report-{person_name.replace(' ','_')}-{date_obj.strftime('%Y-%m-%d')}.pdf"
    pdf.output(pdf_filename)
    
    return pdf_filename
