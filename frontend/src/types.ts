export interface ScannedFile {
  name: string
  path: string
  type: string
}

export interface IncomeItem {
  description: string
  amount: number
  source: string
  type: string
}

export interface DeductionItem {
  description: string
  amount: number
  category: string
}

export interface EstimatedPaymentItem {
  description: string
  amount: number
  date: string
  jurisdiction: string
}

export interface TaxResult {
  documents_analyzed: string[]
  income: IncomeItem[]
  deductions: DeductionItem[]
  estimated_payments: EstimatedPaymentItem[]
  total_income: number
  total_deductions: number
  total_estimated_payments: number
  estimated_taxable_income: number
  summary: string
  notes: string[]
}
