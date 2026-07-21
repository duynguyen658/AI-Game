import { DocumentUpload } from "./upload"; import { PageHeader } from "@/components/layout/page-header";
export const metadata = { title: "Process document" }; export default function NewDocumentPage() { return <div className="space-y-6"><PageHeader title="Process document" description="Upload PDF, DOCX, or TXT for safe extraction and model-assisted review." /><DocumentUpload /></div>; }
