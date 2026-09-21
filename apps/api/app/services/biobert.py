"""BioBERT & spaCy Clinical NLP Service.

Generic clinical entity extraction and assertion detection service.
Processes EHR notes and physician reports, identifies clinical entity spans,
and determines their assertion status (PRESENT, NEGATED, FAMILY_HISTORY, HYPOTHETICAL).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.schemas.model import AssertionStatus, EntityResult, ModelResult, NLPRawOutput

logger = logging.getLogger(__name__)

# Non-clinical structural and grammatical tokens often picked up by generic biomedical models
NON_CLINICAL_STOP_ENTITIES: frozenset[str] = frozenset(
    {
        "patient",
        "pt",
        "pts",
        "mother",
        "father",
        "sister",
        "brother",
        "parent",
        "parents",
        "daughter",
        "son",
        "family",
        "family member",
        "family members",
        "doctor",
        "physician",
        "nurse",
        "history",
        "no history",
        "hx",
        "fhx",
        "examination",
        "physical examination",
        "assessment",
        "plan",
        "hospital",
        "clinic",
        "admission",
        "discharge",
        "consultation",
        "year old",
        "years old",
        "yo",
        "y/o",
        "male",
        "female",
        "man",
        "woman",
        "reports",
        "reported",
        "reporting",
        "diagnose",
        "diagnosed",
        "diagnosing",
        "diagnosis",
        "diagnoses",
        "treated",
        "treatment",
        "prescribed",
        "advised",
        "underwent",
        "evaluated",
        "evaluation",
        "noted",
        "noting",
        "denied",
        "denies",
        "denying",
        "presents",
        "presented",
        "presenting",
        "complains",
        "complained",
        "findings",
        "status",
        "negative",
        "positive",
        "normal",
        "abnormal",
        "rule out",
        "r/o",
        "return to",
        "ed",
        "er",
        "emergency department",
        "today",
        "yesterday",
        "tomorrow",
        "day",
        "days",
        "month",
        "months",
        "year",
        "years",
        "week",
        "weeks",
        "follow up",
        "follow-up",
        "note",
        "notes",
    }
)

# Prefix modifiers that NER models sometimes clump into the entity span
PREFIX_TRIGGERS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"^(?:rule\s+out|r/o|rules\s+out|ruled\s+out)\s+", re.IGNORECASE),
        AssertionStatus.HYPOTHETICAL,
    ),
    (
        re.compile(r"^(?:suspected|possible|probable|potential)\s+", re.IGNORECASE),
        AssertionStatus.HYPOTHETICAL,
    ),
    (
        re.compile(
            r"^(?:no\s+history\s+of|no\s+evidence\s+of|no\s+signs\s+of|negative\s+for|no|without|denies)\s+",
            re.IGNORECASE,
        ),
        AssertionStatus.NEGATED,
    ),
    (
        re.compile(
            r"^(?:family\s+history\s+of|fhx\s+of|fh\s+of|maternal\s+|paternal\s+)\s*",
            re.IGNORECASE,
        ),
        AssertionStatus.FAMILY_HISTORY,
    ),
]

# Patterns for assertion classification
FAMILY_TRIGGERS: list[re.Pattern] = [
    re.compile(
        r"\b(?:family\s+history(?:\s+of)?|fhx(?:\s+of)?|fh(?:\s+of)?|family\s+hx(?:\s+of)?|"
        r"mother|maternal|father|paternal|sister|brother|parent|parents|grandmother|grandfather|"
        r"aunt|uncle|sibling|daughter|son|family\s+members?)\b",
        re.IGNORECASE,
    ),
]

NEGATED_FAMILY_TRIGGERS: list[re.Pattern] = [
    re.compile(
        r"\b(?:no\s+family\s+history|negative\s+family\s+history|denies\s+family\s+history|"
        r"without\s+family\s+history|no\s+fhx|negative\s+fhx)\b",
        re.IGNORECASE,
    )
]

HYPOTHETICAL_TRIGGERS: list[re.Pattern] = [
    re.compile(
        r"\b(?:rule\s+out|r/o|rules\s+out|evaluate\s+for|eval\s+for|suspected|possible|probable|"
        r"differential(?:\s+diagnosis)?|risk\s+of|concern\s+for|if(?:\s+patient|\s+symptoms|\s+pain|\s+fever)?|"
        r"should(?:\s+recur|\s+worsen|\s+develop)?|in\s+(?:the\s+)?event\s+of|as\s+needed\s+for|"
        r"return\s+(?:to\s+ed\s+)?if|potential|questionable|presumed|monitor\s+for)\b",
        re.IGNORECASE,
    ),
]

PRE_NEGATION_TRIGGERS: list[re.Pattern] = [
    re.compile(
        r"\b(?:no|not|denies|denied|denying|negative\s+for|without|w/o|no\s+history\s+of|"
        r"no\s+evidence\s+of|no\s+signs\s+of|free\s+of|never\s+had|never\s+diagnosed\s+with|"
        r"absent|rules\s+out|ruled\s+out|unremarkable\s+for|resolved|has\s+no|shows\s+no)\b",
        re.IGNORECASE,
    ),
]

POST_NEGATION_TRIGGERS: list[re.Pattern] = [
    re.compile(
        r"\b(?:is\s+negative|was\s+negative|ruled\s+out|is\s+absent|was\s+absent|"
        r"unlikely|not\s+seen|unremarkable)\b",
        re.IGNORECASE,
    ),
]

# Conjunctions and punctuation that terminate modifier scope within a sentence
CLAUSE_DELIMITERS = re.compile(
    r"(?:[,;]\s+(?:but|however|although|yet|though|except|nevertheless)\s+|[;\n]+)",
    re.IGNORECASE,
)

# Common clinical entities across major medical domains to augment statistical NER
CANONICAL_CLINICAL_PATTERNS = [
    # Cardiovascular
    {"label": "DISEASE", "pattern": "hypertension"},
    {"label": "DISEASE", "pattern": "acute hypertension"},
    {"label": "DISEASE", "pattern": "hypotension"},
    {"label": "DISEASE", "pattern": "coronary artery disease"},
    {"label": "DISEASE", "pattern": "myocardial infarction"},
    {"label": "DISEASE", "pattern": "acute myocardial infarction"},
    {"label": "DISEASE", "pattern": "heart failure"},
    {"label": "DISEASE", "pattern": "atrial fibrillation"},
    {"label": "DISEASE", "pattern": "angina"},
    {"label": "DISEASE", "pattern": "stroke"},
    {"label": "DISEASE", "pattern": "arrhythmia"},
    {"label": "DISEASE", "pattern": "atherosclerosis"},
    # Respiratory
    {"label": "DISEASE", "pattern": "pneumonia"},
    {"label": "DISEASE", "pattern": "asthma"},
    {"label": "DISEASE", "pattern": "copd"},
    {"label": "DISEASE", "pattern": "bronchitis"},
    {"label": "DISEASE", "pattern": "pulmonary embolism"},
    {"label": "DISEASE", "pattern": "tuberculosis"},
    {"label": "DISEASE", "pattern": "pneumothorax"},
    {"label": "SYMPTOM", "pattern": "dyspnea"},
    {"label": "SYMPTOM", "pattern": "cough"},
    {"label": "SYMPTOM", "pattern": "shortness of breath"},
    {"label": "SYMPTOM", "pattern": "hemoptysis"},
    # Endocrine & Metabolic
    {"label": "DISEASE", "pattern": "diabetes"},
    {"label": "DISEASE", "pattern": "type 1 diabetes"},
    {"label": "DISEASE", "pattern": "type 2 diabetes"},
    {"label": "DISEASE", "pattern": "diabetes mellitus"},
    {"label": "DISEASE", "pattern": "diabetic ketoacidosis"},
    {"label": "DISEASE", "pattern": "hypothyroidism"},
    {"label": "DISEASE", "pattern": "hyperthyroidism"},
    {"label": "DISEASE", "pattern": "hyperlipidemia"},
    {"label": "DISEASE", "pattern": "dyslipidemia"},
    {"label": "DISEASE", "pattern": "obesity"},
    # Oncology
    {"label": "DISEASE", "pattern": "cancer"},
    {"label": "DISEASE", "pattern": "breast cancer"},
    {"label": "DISEASE", "pattern": "lung cancer"},
    {"label": "DISEASE", "pattern": "colon cancer"},
    {"label": "DISEASE", "pattern": "melanoma"},
    {"label": "DISEASE", "pattern": "lymphoma"},
    {"label": "DISEASE", "pattern": "leukemia"},
    {"label": "DISEASE", "pattern": "carcinoma"},
    {"label": "DISEASE", "pattern": "sarcoma"},
    {"label": "DISEASE", "pattern": "tumor"},
    {"label": "DISEASE", "pattern": "neoplasm"},
    {"label": "DISEASE", "pattern": "metastasis"},
    # Neurological
    {"label": "DISEASE", "pattern": "dementia"},
    {"label": "DISEASE", "pattern": "alzheimer's"},
    {"label": "DISEASE", "pattern": "parkinson's"},
    {"label": "DISEASE", "pattern": "epilepsy"},
    {"label": "DISEASE", "pattern": "seizure"},
    {"label": "DISEASE", "pattern": "neuropathy"},
    # Symptoms
    {"label": "SYMPTOM", "pattern": "chest pain"},
    {"label": "SYMPTOM", "pattern": "abdominal pain"},
    {"label": "SYMPTOM", "pattern": "fever"},
    {"label": "SYMPTOM", "pattern": "chills"},
    {"label": "SYMPTOM", "pattern": "headache"},
    {"label": "SYMPTOM", "pattern": "dizziness"},
    {"label": "SYMPTOM", "pattern": "fatigue"},
    {"label": "SYMPTOM", "pattern": "nausea"},
    {"label": "SYMPTOM", "pattern": "vomiting"},
    {"label": "SYMPTOM", "pattern": "edema"},
    # Medications
    {"label": "CHEMICAL", "pattern": "aspirin"},
    {"label": "CHEMICAL", "pattern": "metformin"},
    {"label": "CHEMICAL", "pattern": "lisinopril"},
    {"label": "CHEMICAL", "pattern": "atorvastatin"},
    {"label": "CHEMICAL", "pattern": "insulin"},
    {"label": "CHEMICAL", "pattern": "amoxicillin"},
]


class AssertionDetector:
    """Classifies entity assertions into PRESENT, NEGATED, FAMILY_HISTORY, or HYPOTHETICAL."""

    @staticmethod
    def split_into_clauses(text: str) -> list[tuple[int, int, str]]:
        """Split text into clause segments while tracking their character offsets."""
        clauses = []
        last_idx = 0
        for match in CLAUSE_DELIMITERS.finditer(text):
            start = match.start()
            end = match.end()
            if start > last_idx:
                clauses.append((last_idx, start, text[last_idx:start]))
            last_idx = end
        if last_idx < len(text):
            clauses.append((last_idx, len(text), text[last_idx:]))
        return clauses or [(0, len(text), text)]

    @classmethod
    def get_enclosing_clause(
        cls, sent_text: str, ent_start_in_sent: int, ent_end_in_sent: int
    ) -> tuple[str, str]:
        """Find the clause enclosing the entity span and extract pre/post text."""
        clauses = cls.split_into_clauses(sent_text)
        for c_start, c_end, clause_str in clauses:
            if c_start <= ent_start_in_sent and ent_end_in_sent <= c_end:
                pre = clause_str[: ent_start_in_sent - c_start]
                post = clause_str[ent_end_in_sent - c_start :]
                return pre, post

        # Fallback to entire sentence if boundaries don't cleanly align
        pre = sent_text[:ent_start_in_sent]
        post = sent_text[ent_end_in_sent:]
        return pre, post

    @classmethod
    def determine_assertion(
        cls,
        ent_text: str,
        sent_text: str,
        ent_start_in_sent: int,
        ent_end_in_sent: int,
        negex_flag: bool = False,
    ) -> str:
        """Determine assertion status based on ConText and negspaCy trigger patterns."""
        pre_text, post_text = cls.get_enclosing_clause(
            sent_text, ent_start_in_sent, ent_end_in_sent
        )

        # 1. Negated family history (e.g. "no family history of cancer")
        for pat in NEGATED_FAMILY_TRIGGERS:
            if pat.search(pre_text):
                return AssertionStatus.NEGATED

        # 2. Hypothetical / Uncertainty (e.g. "rule out", "evaluate for", "if", "suspected")
        for pat in HYPOTHETICAL_TRIGGERS:
            if pat.search(pre_text) or pat.search(post_text):
                return AssertionStatus.HYPOTHETICAL

        # 3. Family history (e.g. "mother had", "family history of", "paternal")
        for pat in FAMILY_TRIGGERS:
            if pat.search(pre_text) or pat.search(post_text):
                return AssertionStatus.FAMILY_HISTORY

        # 4. Negation: check pre-negation in clause, post-negation, or negex flag
        for pat in PRE_NEGATION_TRIGGERS:
            if pat.search(pre_text):
                return AssertionStatus.NEGATED

        for pat in POST_NEGATION_TRIGGERS:
            if pat.search(post_text):
                return AssertionStatus.NEGATED

        if negex_flag:
            return AssertionStatus.NEGATED

        # 5. Confirmed present finding
        return AssertionStatus.PRESENT


class BioBERTClinicalNLPService:
    """Clinical NLP Model Service powered by scispaCy, negspaCy, and BioBERT/PubMedBERT.

    Extracts generic clinical entities from any EHR narrative or clinical note,
    assigns assertion statuses, and formats output conforming to ModelResult schema.
    """

    MODEL_ID = "biobert"

    def __init__(
        self,
        spacy_model: str = "en_core_sci_sm",
        transformer_model: str = "dmis-lab/biobert-v1.1",
        device: str | None = None,
        load_transformer: bool = False,
    ) -> None:
        self.spacy_model_name = spacy_model
        self.transformer_model_name = transformer_model
        self.device = device
        self._nlp = None
        self._tokenizer = None
        self._transformer = None

        if load_transformer:
            self._load_transformer()

    def _get_nlp(self):
        """Lazy-load the spaCy / scispaCy pipeline with negspaCy integration."""
        if self._nlp is None:
            import spacy
            from negspacy.negation import Negex

            try:
                nlp = spacy.load(self.spacy_model_name)
            except Exception as err:
                logger.warning(
                    "Could not load '%s' (%s). Falling back to blank 'en' pipeline.",
                    self.spacy_model_name,
                    err,
                )
                nlp = spacy.blank("en")
                if "sentencizer" not in nlp.pipe_names:
                    nlp.add_pipe("sentencizer")

            # Augment pipeline with canonical clinical patterns
            if "entity_ruler" not in nlp.pipe_names:
                ruler_kwargs = {}
                if "ner" in nlp.pipe_names:
                    ruler_kwargs["before"] = "ner"
                ruler = nlp.add_pipe("entity_ruler", **ruler_kwargs)
                ruler.add_patterns(CANONICAL_CLINICAL_PATTERNS)

            # Add negex pipeline component if not already attached
            if "negex" not in nlp.pipe_names:
                try:
                    nlp.add_pipe("negex")
                except Exception:
                    negex_comp = Negex(nlp)
                    nlp.add_pipe(negex_comp)

            self._nlp = nlp
        return self._nlp

    def _load_transformer(self):
        """Load HuggingFace transformer tokenizer and model on demand."""
        if self._transformer is None:
            from transformers import AutoModel, AutoTokenizer

            logger.info("Loading BioBERT transformer model: %s", self.transformer_model_name)
            self._tokenizer = AutoTokenizer.from_pretrained(self.transformer_model_name)
            self._transformer = AutoModel.from_pretrained(self.transformer_model_name)
            if self.device:
                self._transformer = self._transformer.to(self.device)
            self._transformer.eval()
        return self._transformer, self._tokenizer

    def extract_entities(self, text: str) -> list[EntityResult]:
        """Extract generic medical entities and their assertion statuses from text.

        Returns a list of EntityResult objects with exact character spans.
        """
        if not text or not text.strip():
            return []

        nlp = self._get_nlp()
        doc = nlp(text)

        results: list[EntityResult] = []
        seen_spans: set[tuple[int, int]] = set()

        for ent in doc.ents:
            raw_text = ent.text.strip()
            start_char = ent.start_char
            end_char = ent.end_char

            # Filter out non-clinical stopwords or empty matches
            cleaned_text = raw_text.lower().strip(" ,.;:-_()[]{}")
            if not cleaned_text or cleaned_text in NON_CLINICAL_STOP_ENTITIES:
                continue

            # Strip leading trigger words that NER absorbed into the entity span
            assertion_override: str | None = None
            for trigger_pat, trigger_assertion in PREFIX_TRIGGERS:
                match = trigger_pat.match(raw_text)
                if match:
                    prefix_len = match.end()
                    raw_text = raw_text[prefix_len:].strip()
                    start_char += prefix_len
                    assertion_override = trigger_assertion
                    break

            cleaned_after_strip = raw_text.lower().strip(" ,.;:-_()[]{}")
            if (
                not cleaned_after_strip
                or cleaned_after_strip in NON_CLINICAL_STOP_ENTITIES
                or len(raw_text) < 2
            ):
                continue

            # Check duplication
            if (start_char, end_char) in seen_spans:
                continue
            seen_spans.add((start_char, end_char))

            # Determine assertion status
            if assertion_override:
                assertion = assertion_override
            else:
                sent = ent.sent if ent.sent is not None else doc
                ent_start_in_sent = max(0, start_char - sent.start_char)
                ent_end_in_sent = max(0, end_char - sent.start_char)
                negex_flag = getattr(ent._, "negex", False)

                assertion = AssertionDetector.determine_assertion(
                    ent_text=raw_text,
                    sent_text=sent.text,
                    ent_start_in_sent=ent_start_in_sent,
                    ent_end_in_sent=ent_end_in_sent,
                    negex_flag=negex_flag,
                )

            label = ent.label_ if ent.label_ else "ENTITY"

            results.append(
                EntityResult(
                    text=raw_text,
                    label=label,
                    assertion=assertion,
                    start_char=start_char,
                    end_char=end_char,
                )
            )

        return results

    def predict(self, input_data: str | dict[str, Any]) -> ModelResult:
        """Process clinical text and produce standardized ModelResult.

        Accepts either a raw text string or a dict containing a 'text' key.
        """
        text = (
            str(input_data.get("text", ""))
            if isinstance(input_data, dict)
            else str(input_data)
        )

        try:
            entities = self.extract_entities(text)
            raw_output = NLPRawOutput(entities=entities).model_dump()

            return ModelResult(
                model_id=self.MODEL_ID,
                status="success",
                raw_output=raw_output,
            )
        except Exception as exc:
            logger.exception("BioBERT Clinical NLP service failed: %s", exc)
            return ModelResult(
                model_id=self.MODEL_ID,
                status="error",
                raw_output={"error": str(exc), "entities": []},
            )

    def encode(self, texts: list[str]) -> Any:
        """Encode text batch into contextual embedding vectors using BioBERT backbone."""
        import torch

        model, tokenizer = self._load_transformer()
        inputs = tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt",
        )
        if self.device:
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model(**inputs)
            # Pool token embeddings (mean pooling over last hidden state)
            attention_mask = inputs["attention_mask"].unsqueeze(-1)
            token_embeddings = outputs.last_hidden_state
            pooled = torch.sum(token_embeddings * attention_mask, dim=1) / torch.clamp(
                attention_mask.sum(dim=1), min=1e-9
            )

        return pooled.cpu().numpy()
