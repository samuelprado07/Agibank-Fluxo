import PaymentForm from './PaymentForm.jsx'

export default function ReceiptForm({ income, ...props }) {
  return <PaymentForm {...props} isIncome expense={{ ...income, due_date: income.expected_date, payment: income.receipt, payment_version: income.receipt_version }} />
}
