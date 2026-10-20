export type User = {
  id: string;
  email: string;
};

export type Project = {
  id: string;
  name: string;
  created_at: number;
  api_key_prefix: string;
};

export type ProjectCreated = Project & {
  api_key: string;
  connection_string: string;
};

export type ConnectionInfo = {
  id: string;
  name: string;
  connection_string: string;
  api_key_prefix: string;
};

export type CollectionInfo = {
  name: string;
  object_count: number;
  index_kind: string | null;
  index_size: number;
  modalities: string[];
};

export type Explanation = {
  similarity: number;
  confidence: number;
  matched_terms: string[];
  matched_entities: string[];
  matched_keyphrases: string[];
  contributing_field: string;
};

export type QueryResultItem = {
  object_id: string;
  version: number;
  metadata: Record<string, unknown>;
  modalities: Record<string, unknown>;
  score: number | null;
  explanation: Explanation | null;
};

export type QueryResponse = {
  results: QueryResultItem[];
  strategy: string;
  estimated_candidates: number;
};

export type IngestFileResponse = {
  object_ids: string[];
  chunks_created: number;
};

export type ObjectResponse = {
  object_id: string;
  version: number;
  collection: string;
  metadata: Record<string, unknown>;
  modalities: Record<string, unknown>;
};

export type FileSummary = {
  filename: string;
  chunk_count: number;
};

export type DeleteFileResponse = {
  deleted: number;
};

export type VersionHistoryEntry = {
  catalog_version: number;
  action: string;
  segment_id: string;
  timestamp: number;
};
