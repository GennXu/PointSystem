import { points } from './logic'

export type RedeemTemplate = { id: string; name: string; points: number }

export function templateRedemption(template: RedeemTemplate) {
  return { amount: points(template.points), reason: '商品：' + template.name, redeem_template_id: template.id }
}
