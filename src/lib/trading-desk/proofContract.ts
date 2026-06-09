import {
  PROOF_EVIDENCE_CONTRACT,
  PROOF_EVIDENCE_CONTRACT_VERSION,
} from "@/lib/generated/proofEvidenceContract";

export { PROOF_EVIDENCE_CONTRACT_VERSION };
export const PROOF_CLASSES = PROOF_EVIDENCE_CONTRACT.proofClasses;
export const PRODUCTION_EVIDENCE_GROUP_IDS: readonly string[] =
  PROOF_EVIDENCE_CONTRACT.frontendGroups.productionEvidenceGroupIds;
export const EVIDENCE_GROUPS = PROOF_EVIDENCE_CONTRACT.frontendGroups.groups;
export const EVIDENCE_DISPLAY_PRECEDENCE: readonly string[] =
  PROOF_EVIDENCE_CONTRACT.frontendGroups.displayPrecedence;
export const QUOTE_EVIDENCE_CLASSES = PROOF_EVIDENCE_CONTRACT.quoteEvidence.classes;
export const QUOTE_TRUSTED_INTRADAY_TOKENS: readonly string[] =
  PROOF_EVIDENCE_CONTRACT.quoteEvidence.trustedIntradayTokens;
export const QUOTE_DAILY_TOKENS: readonly string[] =
  PROOF_EVIDENCE_CONTRACT.quoteEvidence.dailyTokens;
export const QUOTE_SYNTHETIC_TOKENS: readonly string[] =
  PROOF_EVIDENCE_CONTRACT.quoteEvidence.syntheticTokens;
export const RESEARCH_BACKFILL_IDENTITY_FIELDS: readonly string[] =
  PROOF_EVIDENCE_CONTRACT.researchBackfill.identityFields;
export const RESEARCH_BACKFILL_TOKENS: readonly string[] = PROOF_EVIDENCE_CONTRACT.researchBackfill.tokens;
export const ENTRY_PROOF = PROOF_EVIDENCE_CONTRACT.entryProof;
export const REQUIRED_LIVE_SELECTION_SOURCE =
  PROOF_EVIDENCE_CONTRACT.entryProof.requiredSelectionSource;
export const REQUIRED_SOURCE_SCAN_LINEAGE_FIELDS: readonly string[] =
  PROOF_EVIDENCE_CONTRACT.entryProof.requiredLineageFields;
export const TRUSTED_OPTIONS_SOURCE_LABELS: readonly string[] =
  PROOF_EVIDENCE_CONTRACT.entryProof.trustedOptionsSourceLabels;
export const TRUSTED_OPTIONS_SOURCE_REQUIRED_TOKENS: readonly string[] =
  PROOF_EVIDENCE_CONTRACT.entryProof.trustedOptionsSourceRequiredTokens;
export const PROOF_SOURCE_FIELDS: readonly string[] = PROOF_EVIDENCE_CONTRACT.entryProof.sourceFields;
export const TRUSTED_ENTRY_BASIS_TOKENS: readonly string[] =
  PROOF_EVIDENCE_CONTRACT.entryProof.trustedEntryBasisTokens;
export const UNTRUSTED_ENTRY_BASIS_TOKENS: readonly string[] =
  PROOF_EVIDENCE_CONTRACT.entryProof.untrustedEntryBasisTokens;
export const ENTRY_PRICE_FIELDS: readonly string[] = PROOF_EVIDENCE_CONTRACT.entryProof.entryPriceFields;
export const QUOTE_TIME_FIELDS: readonly string[] = PROOF_EVIDENCE_CONTRACT.entryProof.quoteTimeFields;
export const QUOTE_FRESHNESS_FIELDS: readonly string[] =
  PROOF_EVIDENCE_CONTRACT.entryProof.quoteFreshnessFields;
export const QUOTE_FRESHNESS_REQUIRED =
  PROOF_EVIDENCE_CONTRACT.entryProof.quoteFreshnessRequired;
export const UNTRUSTED_QUOTE_FRESHNESS_TOKENS: readonly string[] =
  PROOF_EVIDENCE_CONTRACT.entryProof.untrustedQuoteFreshnessTokens;
export const TRUSTED_EXIT_BASIS_TOKENS: readonly string[] = PROOF_EVIDENCE_CONTRACT.exitBasis.trustedTokens;
export const UNTRUSTED_EXIT_BASIS_TOKENS: readonly string[] = PROOF_EVIDENCE_CONTRACT.exitBasis.untrustedTokens;
