"""
QTI 2.1 Exporter - Export quizzes in IMS QTI 2.1 format.

QTI (Question and Test Interoperability) is an IMS Global standard for
representing assessments and their results in XML format. It's widely
supported by Learning Management Systems (LMS) like Canvas, Blackboard,
Moodle, and Brightspace.

This exporter creates a QTI 2.1 compliant package containing:
- imsmanifest.xml (package manifest)
- assessment.xml (assessment/test definition)
- Individual question items as XML files

Reference: https://www.imsglobal.org/question/qtiv2p1/imsqti_implv2p1.html
"""

import io
import zipfile
from typing import TYPE_CHECKING, List
from uuid import uuid4
from xml.etree import ElementTree as ET
from xml.dom import minidom

from services.exporters.base import BaseExporter, ExportError
from schemas.export import ExportResult

if TYPE_CHECKING:
    from schemas.export import (
        QuizExportData,
        ExportOptions,
        ExportQuestionMCQ,
        ExportQuestionTrueFalse,
        ExportQuestionFillBlank,
        ExportQuestionMatching,
    )


# QTI 2.1 XML Namespaces
QTI_NAMESPACE = "http://www.imsglobal.org/xsd/imsqti_v2p1"
MANIFEST_NAMESPACE = "http://www.imsglobal.org/xsd/imscp_v1p1"
METADATA_NAMESPACE = "http://www.imsglobal.org/xsd/imsmd_v1p2"

# Register namespaces for cleaner XML output
ET.register_namespace("", QTI_NAMESPACE)
ET.register_namespace("imscp", MANIFEST_NAMESPACE)
ET.register_namespace("imsmd", METADATA_NAMESPACE)


class QtiExporter(BaseExporter):
    """
    Export quizzes in QTI 2.1 format.
    
    Creates a ZIP package containing:
    - imsmanifest.xml: Package manifest with metadata
    - assessment.xml: Assessment definition referencing items
    - items/item_*.xml: Individual question item files
    
    Supported question types:
    - Multiple Choice (choiceInteraction)
    - True/False (choiceInteraction with 2 options)
    - Fill in the Blank (textEntryInteraction)
    - Matching (matchInteraction)
    """
    
    FORMAT_NAME = "qti"
    CONTENT_TYPE = "application/zip"
    FILE_EXTENSION = "zip"
    
    async def export(
        self,
        quiz_data: "QuizExportData",
        options: "ExportOptions"
    ) -> ExportResult:
        """
        Export quiz to QTI 2.1 ZIP package.
        
        Args:
            quiz_data: Quiz data with questions
            options: Export options (include_answer_key affects responseDeclaration)
            
        Returns:
            ExportResult with ZIP file bytes
        """
        try:
            # Create in-memory ZIP file
            zip_buffer = io.BytesIO()
            
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                # Generate unique identifiers for the assessment
                assessment_id = f"assessment_{uuid4().hex[:12]}"
                
                # Create item files and collect references
                item_refs = []
                for idx, question in enumerate(quiz_data.questions, 1):
                    item_id = f"item_{idx}_{uuid4().hex[:8]}"
                    item_xml = self._create_item_xml(question, item_id, idx, options)
                    zf.writestr(f"items/{item_id}.xml", item_xml)
                    item_refs.append((item_id, f"items/{item_id}.xml"))
                
                # Create assessment file
                assessment_xml = self._create_assessment_xml(
                    quiz_data, assessment_id, item_refs
                )
                zf.writestr("assessment.xml", assessment_xml)
                
                # Create manifest file
                manifest_xml = self._create_manifest_xml(
                    quiz_data, assessment_id, item_refs
                )
                zf.writestr("imsmanifest.xml", manifest_xml)
            
            zip_buffer.seek(0)
            content = zip_buffer.getvalue()
            
            return ExportResult(
                content=content,
                content_type=self.CONTENT_TYPE,
                filename=self.generate_filename(quiz_data.title),
            )
            
        except Exception as e:
            raise ExportError(f"QTI export failed: {str(e)}", self.FORMAT_NAME)
    
    def _create_item_xml(
        self,
        question,
        item_id: str,
        question_num: int,
        options: "ExportOptions"
    ) -> str:
        """Create QTI item XML for a single question."""
        
        if question.type == "multiple_choice":
            return self._create_mcq_item(question, item_id, question_num, options)
        elif question.type == "true_false":
            return self._create_true_false_item(question, item_id, question_num, options)
        elif question.type == "fill_blank":
            return self._create_fill_blank_item(question, item_id, question_num, options)
        elif question.type == "matching":
            return self._create_matching_item(question, item_id, question_num, options)
        else:
            # Fallback: treat as MCQ
            return self._create_mcq_item(question, item_id, question_num, options)
    
    def _create_mcq_item(
        self,
        question: "ExportQuestionMCQ",
        item_id: str,
        question_num: int,
        options: "ExportOptions"
    ) -> str:
        """Create QTI choiceInteraction item for MCQ."""
        
        # Root element
        root = ET.Element("assessmentItem", {
            "xmlns": QTI_NAMESPACE,
            "identifier": item_id,
            "title": f"Question {question_num}",
            "adaptive": "false",
            "timeDependent": "false"
        })
        
        # Response declaration (correct answer)
        if options.include_answer_key:
            response_decl = ET.SubElement(root, "responseDeclaration", {
                "identifier": "RESPONSE",
                "cardinality": "single",
                "baseType": "identifier"
            })
            correct_response = ET.SubElement(response_decl, "correctResponse")
            # Find correct answer index
            correct_idx = self._find_correct_option_index(
                question.options, question.correct_answer
            )
            value = ET.SubElement(correct_response, "value")
            value.text = f"choice_{correct_idx}"
        
        # Outcome declaration (score)
        outcome_decl = ET.SubElement(root, "outcomeDeclaration", {
            "identifier": "SCORE",
            "cardinality": "single",
            "baseType": "float"
        })
        default_value = ET.SubElement(outcome_decl, "defaultValue")
        value = ET.SubElement(default_value, "value")
        value.text = "0"
        
        # Item body
        item_body = ET.SubElement(root, "itemBody")
        
        # Question text
        p = ET.SubElement(item_body, "p")
        p.text = question.question
        
        # Choice interaction
        choice_interaction = ET.SubElement(item_body, "choiceInteraction", {
            "responseIdentifier": "RESPONSE",
            "shuffle": "false",
            "maxChoices": "1"
        })
        
        # Add choices
        for idx, opt in enumerate(question.options):
            choice = ET.SubElement(choice_interaction, "simpleChoice", {
                "identifier": f"choice_{idx}"
            })
            choice.text = opt
        
        # Response processing (scoring)
        if options.include_answer_key:
            ET.SubElement(root, "responseProcessing", {
                "template": "http://www.imsglobal.org/question/qti_v2p1/rptemplates/match_correct"
            })
        
        return self._prettify_xml(root)
    
    def _create_true_false_item(
        self,
        question: "ExportQuestionTrueFalse",
        item_id: str,
        question_num: int,
        options: "ExportOptions"
    ) -> str:
        """Create QTI choiceInteraction item for True/False."""
        
        root = ET.Element("assessmentItem", {
            "xmlns": QTI_NAMESPACE,
            "identifier": item_id,
            "title": f"Question {question_num}",
            "adaptive": "false",
            "timeDependent": "false"
        })
        
        # Response declaration
        if options.include_answer_key:
            response_decl = ET.SubElement(root, "responseDeclaration", {
                "identifier": "RESPONSE",
                "cardinality": "single",
                "baseType": "identifier"
            })
            correct_response = ET.SubElement(response_decl, "correctResponse")
            value = ET.SubElement(correct_response, "value")
            value.text = "choice_true" if question.correct_answer else "choice_false"
        
        # Outcome declaration
        outcome_decl = ET.SubElement(root, "outcomeDeclaration", {
            "identifier": "SCORE",
            "cardinality": "single",
            "baseType": "float"
        })
        default_value = ET.SubElement(outcome_decl, "defaultValue")
        value = ET.SubElement(default_value, "value")
        value.text = "0"
        
        # Item body
        item_body = ET.SubElement(root, "itemBody")
        p = ET.SubElement(item_body, "p")
        p.text = question.question
        
        # Choice interaction with True/False options
        choice_interaction = ET.SubElement(item_body, "choiceInteraction", {
            "responseIdentifier": "RESPONSE",
            "shuffle": "false",
            "maxChoices": "1"
        })
        
        true_choice = ET.SubElement(choice_interaction, "simpleChoice", {
            "identifier": "choice_true"
        })
        true_choice.text = "True"
        
        false_choice = ET.SubElement(choice_interaction, "simpleChoice", {
            "identifier": "choice_false"
        })
        false_choice.text = "False"
        
        # Response processing
        if options.include_answer_key:
            ET.SubElement(root, "responseProcessing", {
                "template": "http://www.imsglobal.org/question/qti_v2p1/rptemplates/match_correct"
            })
        
        return self._prettify_xml(root)
    
    def _create_fill_blank_item(
        self,
        question: "ExportQuestionFillBlank",
        item_id: str,
        question_num: int,
        options: "ExportOptions"
    ) -> str:
        """Create QTI textEntryInteraction item for fill-in-the-blank."""
        
        root = ET.Element("assessmentItem", {
            "xmlns": QTI_NAMESPACE,
            "identifier": item_id,
            "title": f"Question {question_num}",
            "adaptive": "false",
            "timeDependent": "false"
        })
        
        # Response declaration with correct answer
        if options.include_answer_key:
            response_decl = ET.SubElement(root, "responseDeclaration", {
                "identifier": "RESPONSE",
                "cardinality": "single",
                "baseType": "string"
            })
            correct_response = ET.SubElement(response_decl, "correctResponse")
            value = ET.SubElement(correct_response, "value")
            value.text = question.correct_answer
        
        # Outcome declaration
        outcome_decl = ET.SubElement(root, "outcomeDeclaration", {
            "identifier": "SCORE",
            "cardinality": "single",
            "baseType": "float"
        })
        default_value = ET.SubElement(outcome_decl, "defaultValue")
        value = ET.SubElement(default_value, "value")
        value.text = "0"
        
        # Item body
        item_body = ET.SubElement(root, "itemBody")
        
        # Question with inline text entry
        p = ET.SubElement(item_body, "p")
        # Replace blank marker with textEntryInteraction
        question_text = question.question
        if "_____" in question_text or "____" in question_text:
            parts = question_text.replace("_____", "____").split("____")
            p.text = parts[0] if parts else ""
            text_entry = ET.SubElement(p, "textEntryInteraction", {
                "responseIdentifier": "RESPONSE",
                "expectedLength": "20"
            })
            if len(parts) > 1:
                text_entry.tail = parts[1]
        else:
            p.text = question_text
            ET.SubElement(item_body, "textEntryInteraction", {
                "responseIdentifier": "RESPONSE",
                "expectedLength": "20"
            })
        
        # Add word bank hint if available
        if question.options:
            hint_p = ET.SubElement(item_body, "p")
            hint_p.text = f"Word bank: {', '.join(question.options)}"
        
        # Response processing
        if options.include_answer_key:
            ET.SubElement(root, "responseProcessing", {
                "template": "http://www.imsglobal.org/question/qti_v2p1/rptemplates/match_correct"
            })
        
        return self._prettify_xml(root)
    
    def _create_matching_item(
        self,
        question: "ExportQuestionMatching",
        item_id: str,
        question_num: int,
        options: "ExportOptions"
    ) -> str:
        """Create QTI matchInteraction item for matching questions."""
        
        root = ET.Element("assessmentItem", {
            "xmlns": QTI_NAMESPACE,
            "identifier": item_id,
            "title": f"Question {question_num}",
            "adaptive": "false",
            "timeDependent": "false"
        })
        
        # Response declaration for matching
        if options.include_answer_key:
            response_decl = ET.SubElement(root, "responseDeclaration", {
                "identifier": "RESPONSE",
                "cardinality": "multiple",
                "baseType": "directedPair"
            })
            correct_response = ET.SubElement(response_decl, "correctResponse")
            
            # Add correct pairs based on correct_answer indices
            for left_idx, right_idx in enumerate(question.correct_answer):
                value = ET.SubElement(correct_response, "value")
                value.text = f"left_{left_idx} right_{right_idx}"
        
        # Outcome declaration
        outcome_decl = ET.SubElement(root, "outcomeDeclaration", {
            "identifier": "SCORE",
            "cardinality": "single",
            "baseType": "float"
        })
        default_value = ET.SubElement(outcome_decl, "defaultValue")
        value = ET.SubElement(default_value, "value")
        value.text = "0"
        
        # Item body
        item_body = ET.SubElement(root, "itemBody")
        
        # Question text
        p = ET.SubElement(item_body, "p")
        p.text = question.question
        
        # Match interaction
        match_interaction = ET.SubElement(item_body, "matchInteraction", {
            "responseIdentifier": "RESPONSE",
            "shuffle": "true",
            "maxAssociations": str(len(question.left))
        })
        
        # Source set (left column)
        source_set = ET.SubElement(match_interaction, "simpleMatchSet")
        for idx, item in enumerate(question.left):
            choice = ET.SubElement(source_set, "simpleAssociableChoice", {
                "identifier": f"left_{idx}",
                "matchMax": "1"
            })
            choice.text = item
        
        # Target set (right column)
        target_set = ET.SubElement(match_interaction, "simpleMatchSet")
        for idx, item in enumerate(question.right):
            choice = ET.SubElement(target_set, "simpleAssociableChoice", {
                "identifier": f"right_{idx}",
                "matchMax": "1"
            })
            choice.text = item
        
        # Response processing
        if options.include_answer_key:
            ET.SubElement(root, "responseProcessing", {
                "template": "http://www.imsglobal.org/question/qti_v2p1/rptemplates/match_correct"
            })
        
        return self._prettify_xml(root)
    
    def _create_assessment_xml(
        self,
        quiz_data: "QuizExportData",
        assessment_id: str,
        item_refs: List[tuple]
    ) -> str:
        """Create QTI assessment XML referencing all items."""
        
        root = ET.Element("assessmentTest", {
            "xmlns": QTI_NAMESPACE,
            "identifier": assessment_id,
            "title": quiz_data.title
        })
        
        # Test part (required container)
        test_part = ET.SubElement(root, "testPart", {
            "identifier": "testPart1",
            "navigationMode": "linear",
            "submissionMode": "individual"
        })
        
        # Assessment section
        section = ET.SubElement(test_part, "assessmentSection", {
            "identifier": "section1",
            "title": quiz_data.title,
            "visible": "true"
        })
        
        # Add item references
        for item_id, item_href in item_refs:
            ET.SubElement(section, "assessmentItemRef", {
                "identifier": item_id,
                "href": item_href
            })
        
        return self._prettify_xml(root)
    
    def _create_manifest_xml(
        self,
        quiz_data: "QuizExportData",
        assessment_id: str,
        item_refs: List[tuple]
    ) -> str:
        """Create IMS Content Package manifest XML."""
        
        root = ET.Element("manifest", {
            "xmlns": MANIFEST_NAMESPACE,
            "xmlns:imsmd": METADATA_NAMESPACE,
            "identifier": f"manifest_{assessment_id}"
        })
        
        # Metadata
        metadata = ET.SubElement(root, "metadata")
        schema = ET.SubElement(metadata, "schema")
        schema.text = "IMS Content"
        schema_version = ET.SubElement(metadata, "schemaversion")
        schema_version.text = "1.2"
        
        # Organizations (empty for QTI)
        ET.SubElement(root, "organizations")
        
        # Resources
        resources = ET.SubElement(root, "resources")
        
        # Assessment resource
        assessment_resource = ET.SubElement(resources, "resource", {
            "identifier": assessment_id,
            "type": "imsqti_test_xmlv2p1",
            "href": "assessment.xml"
        })
        ET.SubElement(assessment_resource, "file", {"href": "assessment.xml"})
        
        # Item resources
        for item_id, item_href in item_refs:
            item_resource = ET.SubElement(resources, "resource", {
                "identifier": item_id,
                "type": "imsqti_item_xmlv2p1",
                "href": item_href
            })
            ET.SubElement(item_resource, "file", {"href": item_href})
        
        return self._prettify_xml(root)
    
    def _find_correct_option_index(self, options: List[str], correct_answer: str) -> int:
        """Find index of correct answer in options list."""
        # Try exact match first
        for idx, opt in enumerate(options):
            if opt == correct_answer:
                return idx
        
        # Try case-insensitive match
        correct_lower = correct_answer.lower().strip()
        for idx, opt in enumerate(options):
            if opt.lower().strip() == correct_lower:
                return idx
        
        # Try letter matching (A, B, C, D)
        if correct_answer.upper() in "ABCD":
            letter_idx = ord(correct_answer.upper()) - ord("A")
            if 0 <= letter_idx < len(options):
                return letter_idx
        
        # Default to first option
        return 0
    
    def _prettify_xml(self, elem: ET.Element) -> str:
        """Convert ElementTree element to pretty-printed XML string."""
        rough_string = ET.tostring(elem, encoding="unicode")
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ", encoding="UTF-8").decode("utf-8")
