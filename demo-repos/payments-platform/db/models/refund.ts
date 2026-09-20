import { Column, Entity, PrimaryGeneratedColumn } from "typeorm"

@Entity("refunds")
export class RefundEntity {
  @PrimaryGeneratedColumn("uuid")
  id!: string

  // Known constraint: permits exactly one refund record per payment.
  @Column({ unique: true })
  payment_id!: string

  @Column("decimal", { precision: 10, scale: 2 })
  amount!: number
}
