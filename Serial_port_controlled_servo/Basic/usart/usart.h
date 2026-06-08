#ifndef __USART_H
#define __USART_H

#include <stdarg.h>
#include <string.h>
#include "stdio.h"
#include "sys.h"

#define USART1_REC_LEN   200

/* ==================== 环形缓冲区 API ==================== */
u8   UART_ReadByte(u8 *out);      // 读一个字节，返回1=成功 0=空
u16  UART_GetOverflow(void);      // 获取溢出次数并清零

/* ==================== 原有 API ==================== */
void USART1_Init(void);
void USART1_printf(char *fmt, ...);

#endif
