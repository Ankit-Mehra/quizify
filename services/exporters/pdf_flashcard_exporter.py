"""
PDF Flashcard Exporter.

Creates printable PDF flashcard sheets with:
- Two-column layout (front on left, back on right)
- Page-break option (front on one page, back on next)
- Optional hints included in back side
- Quizify branding

PERFORMANCE: PDF generation is CPU-bound; uses asyncio.to_thread to avoid
blocking the event loop during doc.build() calls.
"""

import asyncio
import io
import logging
from typing import List

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from schemas.export import (
    ExportResult,
    FlashcardDeckExportData,
    ExportFlashcard,
)
from services.exporters.base import BaseExporter
from services.exporters.constants import (
    QUIZIFY_URL,
)

logger = logging.getLogger(__name__)


class PdfFlashcardExporter(BaseExporter):
    """
    PDF Flashcard Exporter using ReportLab.
    
    Generates printable flashcard sheets with two layout options:
    - Two-column: Front | Back side by side (default)
    - Study mode: Multiple cards per page with foldable layout
    """

    FORMAT_NAME = "pdf_flashcard"
    CONTENT_TYPE = "application/pdf"
    FILE_EXTENSION = "pdf"

    def __init__(self):
        """Initialize PDF exporter with styles."""
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self) -> None:
        """Set up custom paragraph styles for flashcard elements."""
        # Title style
        self.styles.add(ParagraphStyle(
            name='DeckTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            spaceAfter=12,
            alignment=1,  # Center
            textColor=colors.HexColor('#1a1a2e'),
        ))
        
        # Description style
        self.styles.add(ParagraphStyle(
            name='DeckDescription',
            parent=self.styles['Normal'],
            fontSize=12,
            spaceAfter=20,
            alignment=1,  # Center
            textColor=colors.HexColor('#4a4a4a'),
        ))
        
        # Metadata style
        self.styles.add(ParagraphStyle(
            name='DeckMeta',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=6,
            alignment=1,
            textColor=colors.HexColor('#666666'),
        ))
        
        # Card number style
        self.styles.add(ParagraphStyle(
            name='CardNumber',
            parent=self.styles['Normal'],
            fontSize=10,
            fontName='Helvetica-Bold',
            textColor=colors.HexColor('#888888'),
        ))
        
        # Front (question) style
        self.styles.add(ParagraphStyle(
            name='CardFront',
            parent=self.styles['Normal'],
            fontSize=11,
            leading=14,
            textColor=colors.HexColor('#1a1a2e'),
        ))
        
        # Back (answer) style
        self.styles.add(ParagraphStyle(
            name='CardBack',
            parent=self.styles['Normal'],
            fontSize=11,
            leading=14,
            textColor=colors.HexColor('#2d3436'),
        ))
        
        # Hint style
        self.styles.add(ParagraphStyle(
            name='CardHint',
            parent=self.styles['Normal'],
            fontSize=9,
            fontName='Helvetica-Oblique',
            textColor=colors.HexColor('#666666'),
            spaceBefore=6,
        ))
        
        # Section header style
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceBefore=16,
            spaceAfter=12,
            textColor=colors.HexColor('#1a1a2e'),
        ))
        
        # Footer style
        self.styles.add(ParagraphStyle(
            name='FooterText',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#888888'),
            alignment=1,
        ))

    async def export(self, *args, **kwargs) -> ExportResult:
        """
        Export not used for flashcards - use export_flashcards instead.
        
        Raises:
            NotImplementedError: This method is for quiz export only
        """
        raise NotImplementedError("Use export_flashcards for flashcard decks")

    async def export_flashcards(
        self,
        deck_data: FlashcardDeckExportData,
        include_hints: bool = True,
    ) -> ExportResult:
        """
        Export flashcard deck to PDF format.
        
        Creates a two-column layout with front on left and back on right.
        Each page can contain multiple cards for efficient printing.
        
        Args:
            deck_data: Flashcard deck data with cards
            include_hints: Whether to include hints in the export
            
        Returns:
            ExportResult with PDF bytes
        """
        logger.info(f"Exporting flashcard deck '{deck_data.title}' to PDF with {deck_data.card_count} cards")
        
        # Generate PDF in thread to avoid blocking
        pdf_bytes = await asyncio.to_thread(
            self._generate_pdf,
            deck_data,
            include_hints
        )
        
        # Generate filename
        filename = self._sanitize_filename(deck_data.title) + "-flashcards.pdf"
        
        logger.info(f"PDF flashcard export generated: {len(pdf_bytes)} bytes, filename: {filename}")
        
        return ExportResult(
            content=pdf_bytes,
            content_type=self.CONTENT_TYPE,
            filename=filename
        )

    def _generate_pdf(
        self,
        deck_data: FlashcardDeckExportData,
        include_hints: bool
    ) -> bytes:
        """Generate PDF content (runs in thread)."""
        buffer = io.BytesIO()
        
        # Create document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=0.5 * inch,
            leftMargin=0.5 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
        )
        
        # Build story (content)
        story = []
        
        # Add cover/header
        story.extend(self._build_header(deck_data))
        
        # Add cards in two-column table layout
        story.extend(self._build_card_table(deck_data.cards, include_hints))
        
        # Add footer
        story.extend(self._build_footer())
        
        # Build document
        doc.build(story, onFirstPage=self._add_page_elements, onLaterPages=self._add_page_elements)
        
        return buffer.getvalue()

    def _build_header(self, deck_data: FlashcardDeckExportData) -> List:
        """Build the header section with deck title and metadata."""
        story = []
        
        # Title
        story.append(Paragraph(
            self._escape_text(deck_data.title),
            self.styles['DeckTitle']
        ))
        
        # Description if present
        if deck_data.description:
            story.append(Paragraph(
                self._escape_text(deck_data.description),
                self.styles['DeckDescription']
            ))
        
        # Metadata
        meta_text = f"Created: {deck_data.created_at.strftime('%B %d, %Y')} | {deck_data.card_count} cards"
        story.append(Paragraph(meta_text, self.styles['DeckMeta']))
        
        story.append(Spacer(1, 20))
        
        # Column headers
        header_table = Table(
            [['FRONT (Question)', 'BACK (Answer)']],
            colWidths=[3.5 * inch, 3.5 * inch],
        )
        header_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#666666')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LINEBELOW', (0, 0), (-1, -1), 1, colors.HexColor('#cccccc')),
        ]))
        story.append(header_table)
        
        story.append(Spacer(1, 10))
        
        return story

    def _build_card_table(
        self,
        cards: List[ExportFlashcard],
        include_hints: bool
    ) -> List:
        """Build the two-column card table."""
        story = []
        
        for i, card in enumerate(cards, 1):
            # Build front column content
            front_content = [
                Paragraph(f"<b>#{i}</b>", self.styles['CardNumber']),
                Spacer(1, 4),
                Paragraph(self._escape_text(card.front), self.styles['CardFront']),
            ]
            
            # Build back column content
            back_content = [
                Paragraph(self._escape_text(card.back), self.styles['CardBack']),
            ]
            
            # Add hint if present and requested
            if include_hints and card.hint:
                back_content.append(
                    Paragraph(
                        f"<i>Hint: {self._escape_text(card.hint)}</i>",
                        self.styles['CardHint']
                    )
                )
            
            # Create nested table for each column to allow multi-line content
            front_table = Table([[content] for content in front_content], colWidths=[3.3 * inch])
            front_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            
            back_table = Table([[content] for content in back_content], colWidths=[3.3 * inch])
            back_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                ('TOPPADDING', (0, 0), (-1, -1), 0),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ]))
            
            # Main card row
            card_row = Table(
                [[front_table, back_table]],
                colWidths=[3.5 * inch, 3.5 * inch],
            )
            card_row.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 8),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
                ('LINEBEFORE', (1, 0), (1, -1), 0.5, colors.HexColor('#dddddd')),
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f8f9fa')),
            ]))
            
            story.append(card_row)
            story.append(Spacer(1, 6))
        
        return story

    def _build_footer(self) -> List:
        """Build the footer section."""
        story = []
        story.append(Spacer(1, 20))
        story.append(Paragraph(
            f"Generated by Quizify - {QUIZIFY_URL}",
            self.styles['FooterText']
        ))
        return story

    def _add_page_elements(self, canvas, doc):
        """Add page elements (header/footer) to each page."""
        canvas.saveState()
        
        # Add page number at bottom
        page_num = canvas.getPageNumber()
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#888888'))
        canvas.drawCentredString(
            letter[0] / 2,
            0.5 * inch,
            f"Page {page_num}"
        )
        
        canvas.restoreState()

    @staticmethod
    def _escape_text(text: str) -> str:
        """
        Escape and sanitize text for ReportLab Paragraph.
        
        SECURITY: ReportLab's Paragraph component interprets various XML/RML tags.
        Malicious users could craft content with:
        - <img> tags to attempt file inclusion
        - <font> tags to cause rendering issues
        - <para> tags to break layout
        - Other RML tags like <seqreset>, <greek>, etc.
        
        This function escapes ALL XML constructs to ensure only plain text
        is rendered, with controlled line breaks.
        """
        if not text:
            return ""
        
        import re
        
        # First, escape XML special characters (order matters - & first)
        text = text.replace('&', '&amp;')
        text = text.replace('<', '&lt;')
        text = text.replace('>', '&gt;')
        text = text.replace('"', '&quot;')
        text = text.replace("'", '&#39;')
        
        # Remove any null bytes or other control characters (except newlines/tabs)
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        
        # Convert newlines to ReportLab's line break tag
        # This is safe because we've already escaped < and >
        text = text.replace('\n', '<br/>')
        
        # Convert tabs to spaces for consistent rendering
        text = text.replace('\t', '    ')
        
        return text
