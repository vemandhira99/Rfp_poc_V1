'use client'

import { useState, useRef } from 'react'
import { 
  Upload, 
  X, 
  ArrowLeft, 
  FileText, 
  Computer,
  CheckCircle2,
  AlertCircle
} from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface UploadRfpModalProps {
  isOpen: boolean
  onClose: () => void
}

type UploadStep = 'selection' | 'upload' | 'success'

export function UploadRfpModal({ isOpen, onClose }: UploadRfpModalProps) {
  const [step, setStep] = useState<UploadStep>('selection')
  const [isDragging, setIsDragging] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [progress, setProgress] = useState(0)

  const handleClose = () => {
    setStep('selection')
    setFiles([])
    setProgress(0)
    onClose()
  }

  const handleBack = () => {
    setStep('selection')
  }

  const handleSelection = () => {
    setStep('upload')
  }

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const onDragLeave = () => {
    setIsDragging(false)
  }

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      setFiles(Array.from(e.dataTransfer.files))
    }
  }

  const onFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFiles(Array.from(e.target.files))
    }
  }

  const triggerFilePicker = () => {
    fileInputRef.current?.click()
  }

  const [activeDocumentId, setActiveDocumentId] = useState<number | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [currentStage, setCurrentStage] = useState(0)
  
  const ANALYSIS_STAGES = [
    "Uploading Document...",
    "Initializing AI Engine...",
    "Analyzing Document Structure...",
    "Extracting Detailed Metrics...",
    "Synthesizing Strategic Insights...",
    "Finalizing AI Summary..."
  ]

  const handleUpload = async () => {
    if (files.length === 0) return;
    setIsUploading(true)
    setError(null)
    setStep('upload')
    setCurrentStage(0)
    
    try {
      const formData = new FormData()
      formData.append('file', files[0])
      formData.append('title', files[0].name.replace(/\.[^/.]+$/, "")) 
      formData.append('client_name', 'Unknown')
      
      const { API_BASE_URL } = await import('@/lib/api')
      const token = localStorage.getItem('rfp_token');

      // Stage 0: Uploading
      const response = await fetch(`${API_BASE_URL}/uploads/rfp`, {
        method: 'POST',
        headers: {
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        },
        body: formData,
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Upload failed');
      }
      
      const data = await response.json();
      setActiveDocumentId(data.document_id)
      setStep('success') // Move to analysis view
      
      await startAnalysis(data.document_id)

    } catch (err: any) {
      console.error(err);
      setError(err.message || 'An unexpected error occurred during processing.');
    } finally {
      setIsUploading(false)
    }
  }

  const startAnalysis = async (docId: number) => {
    const { API_BASE_URL } = await import('@/lib/api')
    const token = localStorage.getItem('rfp_token');
    
    try {
      setCurrentStage(1)
      await new Promise(r => setTimeout(r, 500))
      
      setCurrentStage(2)
      const parseResponse = await fetch(`${API_BASE_URL}/uploads/rfp/${docId}/parse`, {
        method: 'POST',
        headers: {
          ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        }
      })

      if (!parseResponse.ok) {
        throw new Error('AI Analysis engine failed to initialize');
      }

      // Instead of blocking for minutes, we just show that it's running
      // and give the user the option to close the modal.
      setCurrentStage(3)
      await new Promise(r => setTimeout(r, 500))
      
      // Stop the modal loader and show background message
      setStep('success')
      
    } catch (err: any) {
      setError(err.message)
      setStep('success') 
    }
  }

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[550px] p-0 overflow-hidden border-none shadow-2xl bg-white rounded-2xl">
        <div className="p-8">
          <div className="flex justify-between items-center mb-6">
            <DialogTitle className="text-2xl font-bold text-zinc-900">
              {error ? 'Processing Error' : step === 'success' ? 'AI Analysis in Progress' : 'Upload RFP Document'}
            </DialogTitle>
          </div>

          {error ? (
            <div className="py-6 flex flex-col items-center text-center space-y-6">
              <div className="w-20 h-20 rounded-full bg-rose-50 flex items-center justify-center">
                <AlertCircle className="w-10 h-10 text-rose-500" />
              </div>
              <div className="space-y-2">
                <h3 className="text-xl font-bold text-zinc-900">Analysis Halted</h3>
                <p className="text-zinc-500 max-w-xs mx-auto text-sm">{error}</p>
              </div>
              <div className="flex flex-col w-full gap-2">
                {activeDocumentId ? (
                  <Button 
                    onClick={() => {
                      setError(null)
                      startAnalysis(activeDocumentId)
                    }}
                    className="w-full h-12 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-bold"
                  >
                    Resume Analysis
                  </Button>
                ) : (
                  <Button 
                    onClick={() => {
                      setError(null)
                      setStep('upload')
                    }}
                    className="w-full h-12 bg-zinc-900 hover:bg-zinc-800 text-white rounded-xl font-bold"
                  >
                    Try Again
                  </Button>
                )}
                <Button 
                  variant="ghost"
                  onClick={handleClose}
                  className="w-full h-10 text-zinc-500 text-xs"
                >
                  Close & Check Dashboard Later
                </Button>
              </div>
            </div>
          ) : step === 'selection' ? (
            <div className="space-y-6">
              <p className="text-zinc-500 font-medium">Choose where to upload your RFP from:</p>
              
              <button 
                onClick={handleSelection}
                className="w-full flex items-center gap-6 p-6 rounded-2xl border border-zinc-100 bg-white hover:border-blue-200 hover:bg-blue-50/30 transition-all group text-left shadow-sm hover:shadow-md"
              >
                <div className="w-14 h-14 rounded-2xl bg-blue-50 flex items-center justify-center group-hover:bg-blue-100 transition-colors">
                  <Upload className="w-7 h-7 text-blue-600" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-zinc-900 group-hover:text-blue-700 transition-colors">Upload from Computer</h3>
                  <p className="text-sm text-zinc-500 mt-1">Select PDF, DOCX, or other document files from your device</p>
                </div>
              </button>
            </div>
          ) : step === 'upload' ? (
            <div className="space-y-6">
              {!isUploading && (
                <button 
                  onClick={handleBack}
                  className="flex items-center text-sm font-semibold text-zinc-500 hover:text-zinc-900 transition-colors gap-2"
                >
                  <ArrowLeft className="w-4 h-4" />
                  Back to options
                </button>
              )}

              <div 
                onDragOver={!isUploading ? onDragOver : undefined}
                onDragLeave={!isUploading ? onDragLeave : undefined}
                onDrop={!isUploading ? onDrop : undefined}
                onClick={!isUploading ? triggerFilePicker : undefined}
                className={cn(
                  "relative border-2 border-dashed rounded-2xl p-12 transition-all flex flex-col items-center justify-center text-center",
                  !isUploading && "cursor-pointer hover:bg-zinc-50 hover:border-zinc-300",
                  isDragging 
                    ? "border-blue-400 bg-blue-50/50" 
                    : "border-zinc-200 bg-zinc-50/50",
                  files.length > 0 && "border-blue-200 bg-blue-50/30",
                  isUploading && "opacity-50 cursor-not-allowed"
                )}
              >
                <input 
                  type="file" 
                  ref={fileInputRef} 
                  onChange={onFileSelect} 
                  className="hidden" 
                  multiple 
                  accept=".pdf,.docx,.doc,.txt"
                  disabled={isUploading}
                />
                
                <div className="w-16 h-16 rounded-full bg-white shadow-sm flex items-center justify-center mb-4 border border-zinc-100">
                  <Upload className={cn("w-8 h-8", files.length > 0 ? "text-blue-600" : "text-zinc-400")} />
                </div>

                {files.length > 0 ? (
                  <div className="space-y-2">
                    <p className="font-bold text-zinc-900">
                      {files.length === 1 ? files[0].name : `${files.length} files selected`}
                    </p>
                    <p className="text-xs text-zinc-500">{isUploading ? 'Preparing upload...' : 'Click to change selection'}</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <p className="text-lg font-bold text-zinc-900">Click to browse or drag and drop</p>
                    <p className="text-sm text-zinc-500">Supported formats: PDF, DOCX, DOC, TXT (Max 50MB)</p>
                  </div>
                )}
              </div>

              <div className="flex flex-col sm:flex-row gap-3 pt-2">
                <Button 
                  onClick={handleUpload}
                  disabled={files.length === 0 || isUploading}
                  className="flex-1 h-12 bg-blue-600 hover:bg-blue-700 text-white rounded-xl font-bold shadow-lg shadow-blue-200 disabled:opacity-50 disabled:shadow-none"
                >
                  {isUploading ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin mr-2" />
                      {ANALYSIS_STAGES[currentStage]}
                    </>
                  ) : (
                    <>
                      <Upload className="w-4 h-4 mr-2" />
                      Upload & Analyze
                    </>
                  )}
                </Button>
                {!isUploading && (
                  <Button 
                    variant="outline" 
                    onClick={handleClose}
                    className="h-12 border-zinc-200 text-zinc-700 hover:bg-zinc-50 font-bold rounded-xl px-8"
                  >
                    Cancel
                  </Button>
                )}
              </div>
            </div>
          ) : (
            <div className="py-8 flex flex-col items-center text-center space-y-8">
              <div className="relative">
                  <div className="w-24 h-24 rounded-full bg-blue-50 flex items-center justify-center animate-in zoom-in duration-500">
                    <Computer className="w-12 h-12 text-blue-500" />
                  </div>
                  <div className="absolute top-0 right-0 w-6 h-6 bg-emerald-500 border-4 border-white rounded-full animate-pulse" />
              </div>

              <div className="space-y-3 w-full">
                <div className="space-y-1">
                  <h3 className="text-xl font-bold text-zinc-900">
                    Analysis Running in Background
                  </h3>
                  <p className="text-sm text-zinc-500">
                    Your RFP was uploaded successfully and is now being analyzed. You can safely close this window.
                  </p>
                </div>
              </div>

              <div className="pt-4 w-full flex flex-col gap-3 animate-in fade-in slide-in-from-bottom-4 duration-1000">
                <Button 
                  onClick={() => {
                    handleClose()
                  }}
                  className="w-full h-14 bg-zinc-900 hover:bg-zinc-800 text-white rounded-xl font-bold shadow-xl shadow-zinc-200"
                >
                  View Dashboard
                </Button>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
