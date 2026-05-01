export type MailAttachment = {
  name: string;
  contentType: string;
  size: number;
  id: string;
  contentBase64: string;
};

export type MailSnapshot = {
  subject: string;
  from: string;
  body: string;
  attachments: MailAttachment[];
};

export type PipelineStepStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "skipped";

export type PipelineStepProgress = {
  name: string;
  status: PipelineStepStatus;
  detail: string;
  updated_at: string | null;
};

export type PipelineProgressStatus = "running" | "completed" | "failed";

export type PipelineProgress = {
  review_id: string;
  status: PipelineProgressStatus;
  current_step: string;
  current_detail: string;
  progress_percent: number;
  updated_at: string;
  steps: PipelineStepProgress[];
  result: CreateReviewResponse | null;
  error: string | null;
};

export type CreateReviewResponse = {
  review_id: string;
  review_url: string;

  draft_pdf_url: string;
  draft_pdf_filename: string;

  final_pdf_url?: string;
  final_pdf_filename?: string;

  status_url?: string;
  status?: PipelineProgressStatus;
  summary?: Record<string, unknown>;
  progress?: PipelineProgress;
};


export type PendingReview = {
  review: CreateReviewResponse;
  mailSubject: string;
  sender: string;
  createdAt: string;
};