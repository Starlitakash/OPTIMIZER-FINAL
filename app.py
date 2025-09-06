import os
import re
import fitz
import streamlit as st
import requests
from groq import Groq
from dotenv import load_dotenv
from io import BytesIO
from streamlit_lottie import st_lottie
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import letter
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.colors import black
from reportlab.lib.units import inch

st.set_page_config(
    page_title="Optimizr - AI Resume Reviewer",
    page_icon="🚀",
    layout="wide"
)

if 'resume_text' not in st.session_state:
    st.session_state['resume_text'] = None
if 'job_description' not in st.session_state:
    st.session_state['job_description'] = None
if 'feedback_generated' not in st.session_state:
    st.session_state['feedback_generated'] = False
if 'original_feedback' not in st.session_state:
    st.session_state['original_feedback'] = ""
if 'improved_resume_markdown' not in st.session_state:
    st.session_state['improved_resume_markdown'] = ""
if 'improved_resume_pdf_bytes' not in st.session_state:
    st.session_state['improved_resume_pdf_bytes'] = None

load_dotenv()
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    st.error("GROQ_API_KEY not found in .env file. Please add it and restart the app.")
    st.stop()
client = Groq(api_key=api_key)

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='NameStyle', fontName='Helvetica-Bold', fontSize=18, leading=22, alignment=TA_CENTER, spaceAfter=4))
styles.add(ParagraphStyle(name='ContactStyle', fontName='Helvetica', fontSize=10, leading=12, alignment=TA_CENTER, spaceAfter=12))
styles.add(ParagraphStyle(name='SectionHeaderStyle', fontName='Helvetica-Bold', fontSize=12, leading=14, spaceBefore=10, spaceAfter=2, textColor=black))
styles.add(ParagraphStyle(name='JobTitleStyle', fontName='Helvetica-Bold', fontSize=11, leading=14))
styles.add(ParagraphStyle(name='DateLocationStyle', fontName='Helvetica', fontSize=11, leading=14, alignment=TA_RIGHT))
styles.add(ParagraphStyle(name='BodyTextStyle', fontName='Helvetica', fontSize=11, leading=14, spaceAfter=6, alignment=TA_LEFT))
styles.add(ParagraphStyle(name='BulletStyle', fontName='Helvetica', fontSize=11, leading=14, spaceAfter=4, leftIndent=20, bulletIndent=10))

def load_lottieurl(url: str):
    r = requests.get(url)
    if r.status_code != 200:
        return None
    return r.json()

def extract_text_from_pdf(pdf_file):
    try:
        pdf_document = fitz.open(stream=pdf_file.read(), filetype="pdf")
        text = "".join(page.get_text() for page in pdf_document)
        pdf_document.close()
        return text
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return None

def get_resume_feedback_groq(resume_text, job_description):
    prompt = f"""
    You are an expert career coach. Analyze the resume against the job description.
    Provide clear, constructive feedback in Markdown format, using these exact sections:
    1.  **## Overall Match Score:** A percentage from 1-100% and a 2-sentence summary.
    2.  **## Keyword Analysis:** Two lists: '✅ Keywords Found' and '❌ Keywords Missing'.
    3.  **## Actionable Suggestions:** 3-4 specific, bullet-pointed suggestions for improvement.
    4.  **## Section-Specific Feedback:** Comments on Education, Experience, and Skills.
    5.  **## Impactful Rewrite Example:** Rewrite one weak bullet point to be more impactful.

    ---
    **Job Description:**
    {job_description}
    ---
    **Resume Text:**
    {resume_text}
    ---
    """
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "system", "content": "You are an expert career coach."}, {"role": "user", "content": prompt}],
            temperature=0.5,
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Error calling Groq API for feedback: {e}")
        return "Sorry, there was an error processing your request with the AI."

def get_improved_resume_groq(resume_text, job_description):
    prompt = f"""
    You are an expert resume writer. Rewrite the entire resume provided to be impactful and tailored for the given job description.
    
    **Crucially, prefix each line with a specific tag to identify its type. Use these exact tags and format:**
    - `NAME: ` for the full name.
    - `CONTACT: ` for the contact line (e.g., Email | Phone | LinkedIn).
    - `HEADER: ` for section headers (e.g., SUMMARY, EXPERIENCE, EDUCATION, SKILLS). The header itself should be in all caps.
    - `JOB: ` for a job title or degree title (e.g., Senior Software Engineer).
    - `DATE: ` for the corresponding date and location (e.g., Google | Mountain View, CA | May 2022 - Present).
    - `BULLET: ` for bullet points describing accomplishments, starting with a strong action verb.
    - `TEXT: ` for any other plain text, like a professional summary paragraph.
    - `SKILLS: ` for a line containing a list of skills (e.g., Python, SQL, AWS, Docker).

    Do NOT include any introductory or concluding text. Just output the tagged resume content.

    ---
    **Job Description:**
    {job_description}
    ---
    **Original Resume Text:**
    {resume_text}
    ---
    """
    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "system", "content": "You are an expert resume writer."}, {"role": "user", "content": prompt}],
            temperature=0.7,
        )
        return response.choices[0].message.content.replace("- ", "BULLET: ")
    except Exception as e:
        st.error(f"Error calling Groq API for improved resume: {e}")
        return "Sorry, there was an error generating the improved resume."

def create_pdf_from_markdown(tagged_text):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=0.75*inch, rightMargin=0.75*inch, topMargin=0.5*inch, bottomMargin=0.5*inch)
    story = []
    lines = tagged_text.strip().split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        tag, content = line.split(': ', 1) if ': ' in line else ('FALLBACK', line)
        if tag == 'NAME':
            story.append(Paragraph(content, styles['NameStyle']))
        elif tag == 'CONTACT':
            story.append(Paragraph(content, styles['ContactStyle']))
        elif tag == 'HEADER':
            story.append(Paragraph(content, styles['SectionHeaderStyle']))
            from reportlab.platypus import Flowable
            class Line(Flowable):
                def __init__(self, width, height=0):
                    Flowable.__init__(self)
                    self.width = width
                    self.height = height
                def draw(self):
                    self.canv.line(0, self.height, self.width, self.height)
            story.append(Line(doc.width))
            story.append(Spacer(1, 4))
        elif tag == 'JOB':
            story.append(Paragraph(content, styles['JobTitleStyle']))
        elif tag == 'DATE':
            if story and hasattr(story[-1], 'style') and story[-1].style.name == 'JobTitleStyle':
                job_title_p = story.pop(-1)
                table_data = [[job_title_p, Paragraph(content, styles['DateLocationStyle'])]]
                table = Table(table_data, colWidths=[doc.width * 0.7, doc.width * 0.3])
                table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),]))
                story.append(table)
                story.append(Spacer(1, 4))
            else:
                 story.append(Paragraph(content, styles['DateLocationStyle']))
        elif tag == 'BULLET':
            story.append(Paragraph(content, styles['BulletStyle'], bulletText='•'))
        elif tag in ['TEXT', 'SKILLS', 'FALLBACK']:
            story.append(Paragraph(content, styles['BodyTextStyle']))
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

st.title("🚀 Optimizr")
st.subheader("Your Career, Optimized.", anchor=False)

st.info(
    "**Privacy Notice:** Your resume and job description are processed in memory and are "
    "**never stored**. All data is cleared after you close the browser tab."
)
st.markdown("---")

uploaded_resume = st.file_uploader("1. Upload your Resume (PDF)", type=["pdf"])
job_description_input = st.text_area("2. Paste the Job Description", height=250)

if st.button("Analyze My Resume", use_container_width=True, type="primary"):
    if uploaded_resume is not None and job_description_input:
        placeholder = st.empty()
        lottie_url = "https://lottie.host/21473236-e631-4453-a131-a182a466a9c2/j23a7yYj29.json"
        lottie_animation = load_lottieurl(lottie_url)
        with placeholder.container():
            st.markdown("### Optimizr is working its magic...")
            if lottie_animation:
                st_lottie(lottie_animation, height=200, key="lottie_upload")
            else:
                st.info("Please wait while we process your resume...")
        resume_text = extract_text_from_pdf(uploaded_resume)
        if resume_text:
            st.session_state['resume_text'] = resume_text
            st.session_state['job_description'] = job_description_input
            feedback = get_resume_feedback_groq(resume_text, job_description_input)
            st.session_state['original_feedback'] = feedback
            st.session_state['feedback_generated'] = True
            st.session_state['improved_resume_markdown'] = ""
            st.session_state['improved_resume_pdf_bytes'] = None
        else:
            st.session_state['feedback_generated'] = False
        placeholder.empty()
    else:
        st.warning("Please upload a resume and paste a job description to get started.")
        st.session_state['feedback_generated'] = False

st.markdown("---")

if st.session_state['feedback_generated']:
    st.header("Your Personalized Feedback ✨", anchor=False)
    st.markdown("**Clearly structured feedback, possibly section-wise (Education, Experience, Skills, etc.)**")
    try:
        score_match = re.search(r"(\d+)%", st.session_state['original_feedback'])
        if score_match:
            score = int(score_match.group(1))
            st.progress(score / 100, text=f"Match Score: {score}%")
    except (ValueError, IndexError):
        pass
    st.markdown(st.session_state['original_feedback'])
    st.markdown("---")
    st.header("Optimized Resume Draft 📄", anchor=False)
    st.markdown("**Optionally, generate an improved version of the resume.**")
    if st.session_state.get('improved_resume_markdown'):
        with st.expander("Show Raw AI Output for Debugging"):
            st.text_area("Tagged Text from AI:", st.session_state['improved_resume_markdown'], height=250)
        if st.session_state.get('improved_resume_pdf_bytes'):
            st.download_button(
                label="Download Optimized Resume (PDF)",
                data=st.session_state['improved_resume_pdf_bytes'],
                file_name="optimized_resume.pdf",
                mime="application/pdf",
                use_container_width=True
            )
    else:
        if st.button("Generate Improved Resume Draft", use_container_width=True):
            with st.spinner("Crafting your optimized resume..."):
                improved_markdown = get_improved_resume_groq(st.session_state['resume_text'], st.session_state['job_description'])
                st.session_state['improved_resume_markdown'] = improved_markdown
                pdf_bytes = create_pdf_from_markdown(improved_markdown)
                st.session_state['improved_resume_pdf_bytes'] = pdf_bytes
                st.rerun()
else:
    st.info("Upload your resume and the job description to receive personalized feedback.")
