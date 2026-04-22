using System.Collections.Generic;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;

public static class FiservPayment
{
    public static async Task<Dictionary<string, object?>> CreatePaymentAsync(string url)
    {
        var body = new
        {
            requestType = "PaymentCardSaleTransaction",
            transactionAmount = new { total = "13", currency = "GBP" },
            paymentMethod = new
            {
                paymentCard = new
                {
                    number = "1234********1234",
                    securityCode = "123",
                    expiryDate = new { month = "02", year = "22" },
                },
            },
        };

        using var paymentResponse = await SignedClient.FetchWithSignatureAsync(
            SignedClient.Key, SignedClient.Secret, HttpMethod.Post, url, body);
        paymentResponse.EnsureSuccessStatusCode();

        var responseBody = await paymentResponse.Content.ReadAsStringAsync();

        var result = new Dictionary<string, object?>
        {
            ["requestName"] = "Payment POST - Creating the payment request",
        };

        using var paymentData = JsonDocument.Parse(responseBody);
        foreach (var prop in paymentData.RootElement.EnumerateObject())
        {
            result[prop.Name] = prop.Value.Clone();
        }

        return result;
    }
}
