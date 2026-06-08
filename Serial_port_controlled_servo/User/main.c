/**
 * 双舵机云台控制 (Pan/Tilt)
 * 硬件: STM32F103C8T6
 *   舵机1 (PAN  转向底座): PA0 = TIM2_CH1
 *   舵机2 (TILT 俯仰关节): PA1 = TIM2_CH2
 *
 * 串口协议 (115200, 8N1):
 *   P<角度>\n  设置PAN  例: P60\n
 *   T<角度>\n  设置TILT 例: T45\n
 *   R\n        复位到中点
 */

#include "stm32f10x.h"
#include "usart.h"
#include "delay.h"
#include "stdio.h"
#include "string.h"
#include "stdlib.h"
#include "steer.h"

/* ==================== 命令缓冲区 ==================== */
#define CMD_BUF_SIZE  16

char    cmd_buf[CMD_BUF_SIZE];
uint8_t cmd_len = 0;

/* ==================== 串口命令解析 ==================== */
static void parse_command(char *buf, uint8_t len)
{
    if (len == 0) return;

    /* 回显 */
    printf("[DBG] got \"");
    for (uint8_t k = 0; k < len; k++) {
        if      (buf[k] == '\r') printf("\\r");
        else if (buf[k] == '\n') printf("\\n");
        else                     printf("%c", buf[k]);
    }
    printf("\" (len=%d)\r\n", len);

    /* 跳过前导空白 */
    uint8_t i = 0;
    while (i < len && (buf[i] == ' ' || buf[i] == '\r' || buf[i] == '\n')) i++;
    if (i >= len) return;

    char cmd = buf[i++];

    while (i < len && buf[i] == ' ') i++;

    if (cmd == 'R' || cmd == 'r')
    {
        Steer_SetBoth(90, 90);
        printf("[OK] Reset -> PAN=90 TILT=90\r\n");
        return;
    }

    if ((cmd == 'P' || cmd == 'p' || cmd == 'T' || cmd == 't') && i < len)
    {
        char num_str[5] = {0};
        uint8_t j = 0;
        while (i < len && j < 4 && buf[i] >= '0' && buf[i] <= '9')
        {
            num_str[j++] = buf[i++];
        }
        if (j == 0) {
            printf("[ERR] no number after '%c'\r\n", cmd);
            return;
        }

        uint16_t angle = atoi(num_str);
        uint16_t pulse = 500 + (uint32_t)angle * 2000 / 180;

        if (cmd == 'P' || cmd == 'p')
        {
            Steer_SetPan(angle);
            printf("[OK] PAN=%d (pulse=%d us)\r\n", Steer_GetPan(), pulse);
        }
        else
        {
            Steer_SetTilt(angle);
            printf("[OK] TILT=%d (pulse=%d us)\r\n", Steer_GetTilt(), pulse);
        }
    }
    else
    {
        printf("[ERR] unknown cmd: '%c' (0x%02X)\r\n", cmd, (uint8_t)cmd);
    }
}

/* ==================== 主函数 ==================== */
int main(void)
{
    USART1_Init();
    Steer_Init();
    delay_init();

    Steer_SetBoth(90, 90);

    printf("\r\n================================\r\n");
    printf("  Pan/Tilt 2-Servo Controller\r\n");
    printf("  PAN  -> PA0 (TIM2_CH1)\r\n");
    printf("  TILT -> PA1 (TIM2_CH2)\r\n");
    printf("  UART -> 115200,8N1\r\n");
    printf("  Send: P60  T45  R  + Enter\r\n");
    printf("================================\r\n\r\n");

    memset(cmd_buf, 0, CMD_BUF_SIZE);

    while (1)
    {
        u8 byte;
        while (UART_ReadByte(&byte))       // 环形缓冲区有数据
        {
            char ch = (char)byte;

            if (ch == '\n' || ch == '\r')
            {
                if (cmd_len > 0)
                {
                    cmd_buf[cmd_len] = '\0';
                    parse_command(cmd_buf, cmd_len);
                    cmd_len = 0;
                    memset(cmd_buf, 0, CMD_BUF_SIZE);
                }
            }
            else if (cmd_len < CMD_BUF_SIZE - 1)
            {
                cmd_buf[cmd_len++] = ch;
            }
            else
            {
                printf("[WARN] buffer overflow\r\n");
                cmd_len = 0;
                memset(cmd_buf, 0, CMD_BUF_SIZE);
            }
        }

        /* 溢出告警 */
        u16 ov = UART_GetOverflow();
        if (ov > 0) {
            printf("[WARN] RX overflow x%d\r\n", ov);
        }

        delay_ms(2);
    }
}
